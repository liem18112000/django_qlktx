from collections import defaultdict
from sqlite3 import IntegrityError

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from import_export import fields, resources

from backend.building_utils import BuildingUtils
from backend.helper import RoomAssignmentHelper
from backend.models import Student, Room, Building, Platoon
from backend.room_cache import RoomAssignmentCache
from backend.signals import create_building_floors_and_rooms
from backend.student_utils import StudentUtils


class BaseResource(resources.ModelResource):
    """
    A base resource class that provides generic filtering logic for before_export.
    Other resource classes can inherit from this to apply dynamic filtering.
    """

    exclude_from_export = ("id",)  # Default fields to exclude from export

    def get_export_fields(self):
        """
        Dynamically removes fields listed in `exclude_from_export` from export.
        """
        fields = super().get_export_fields()
        return [field for field in fields if field.column_name not in self.exclude_from_export]

    def filter_export(self, queryset, **kwargs):
        """
        Generic filtering logic: Filters any queryset based on export form selections.
        """

        export_form = kwargs.get("export_form")

        if export_form and export_form.is_valid():

            # Get model fields dynamically
            model_fields = {field.name for field in queryset.model._meta.get_fields()}

            # Build filter criteria only for valid fields
            filter_criteria = {
                f"{key}__in": value for key, value in export_form.cleaned_data.items()
                if key in model_fields and value
            }

            if filter_criteria:
                return queryset.filter(**filter_criteria)

        return queryset


class StudentResource(BaseResource):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.buildings_list = list()
        self.assign_direct = None
        self.fill_partial_first = None
        self.selected_buildings = None
        self.fill_empty_first = None
        self.dict_last_room = defaultdict()
        self.assigned_students = list()

    class Meta:
        model = Student
        import_id_fields = (
            "building",
            "room",
            "full_name",
            "gender",
            "platoon",
            "squad",
            "position",
            "phone_number",
            "headmaster",
            "id"
        )
        export_order = (
            "building",
            "room",
            "full_name",
            "gender",
            "platoon",
            "squad",
            "position",
            "phone_number",
            "headmaster",
        )
        export_fields = (
            "building",
            "room",
            "full_name",
            "gender",
            "platoon",
            "squad",
            "position",
            "phone_number",
            "headmaster",
        )

    building = fields.Field(
        column_name="Tòa nhà",
        attribute="building",
    )

    room = fields.Field(
        column_name="Phòng",
        attribute="room_code",
    )

    full_name = fields.Field(
        attribute="full_name",
        column_name="Họ và tên"
    )

    gender = fields.Field(
        attribute="gender",
        column_name="Giới tính"
    )

    platoon = fields.Field(
        attribute="platoon",
        column_name="Trung đội"
    )

    squad = fields.Field(
        attribute="squad",
        column_name="Tiểu đội"
    )

    position = fields.Field(
        attribute="position",
        column_name="Chức vụ"
    )

    phone_number = fields.Field(
        attribute="phone_number",
        column_name="Số điện thoại"
    )

    headmaster = fields.Field(
        attribute="headmaster",
        column_name="Chủ nhiệm Trung đội"
    )

    def dehydrate_room(self, instance):
        try:
            return instance.room.room_code
        except Exception as e:
            return "N/A"

    def dehydrate_building(self, instance):
        try:
            return instance.room.building.name
        except Exception as e:
            return "N/A"

    def before_import_row(self, row, **kwargs):
        """
        Convert the platoon name (string) to a Platoon instance before import.
        """
        if "Trung đội" in row:
            try:
                # Look up Platoon by name
                platoon_instance = Platoon.objects.get(name=row["Trung đội"])
                row["Trung đội"] = platoon_instance

            except Platoon.DoesNotExist:
                raise ValueError(f"Platoon '{row['Trung đội']}' does not exist. Please check your data.")

        if row.get("Số điện thoại"):
            row["Số điện thoại"] = str(row["Số điện thoại"])

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        """
        Arrange students within the same platoon by squad order from 1 to N.
        Move female students ('Giới tính' = 'Nữ') to the last rows within their platoon.
        Store the selected buildings at the beginning of the import process.
        """
        self.selected_buildings = kwargs.get("selected_building", None)
        self.fill_empty_first = bool(kwargs.get("fill_empty_first", False))
        self.fill_partial_first = bool(kwargs.get("fill_partial_first", True))
        self.dict_last_room = RoomAssignmentHelper.get_last_roon_have_students()
        RoomAssignmentHelper.unlock_empty_rooms()

        print("self.fill_empty_first", self.fill_empty_first)
        print("self.fill_partial_first", self.fill_partial_first)
        print("dict_last_room", self.dict_last_room)

        # Convert dataset to a list of dictionaries for easier sorting
        data_list = [dict(zip(dataset.headers, row)) for row in dataset]

        # Nhóm theo Trung đội (nếu không có thì mặc định)
        platoon_groups = defaultdict(list)
        for item in data_list:
            platoon = item.get("Trung đội ", "").strip() or "Default"
            platoon_groups[platoon].append(item)

        sorted_final = []

        for platoon_name in sorted(platoon_groups.keys()):
            members = platoon_groups[platoon_name]

            # Nhóm thành viên theo Tiểu đội
            squad_map = defaultdict(list)
            for m in members:
                squad_number = int(m.get("Tiểu đội", 0))
                squad_map[squad_number].append(m)

            selected_squad_members = []
            used_ids = set()

            # Giai đoạn 1: chọn 1 người từ mỗi Tiểu đội (ưu tiên Nam), theo thứ tự
            for squad_number in sorted(squad_map.keys()):
                candidates = squad_map[squad_number]
                male = next((c for c in candidates if c.get("Giới tính", "").strip() != "Nữ"), None)
                chosen = male or candidates[0]
                selected_squad_members.append(chosen)
                used_ids.add(id(chosen))

            # Giai đoạn 2: phần còn lại
            remaining_members = [m for m in members if id(m) not in used_ids]

            # Sắp phần còn lại: Tiểu đội tăng dần, Nam trước Nữ
            remaining_sorted = sorted(
                remaining_members,
                key=lambda x: (
                    int(x.get("Tiểu đội", 0)),  # Theo số tiểu đội
                    x.get("Giới tính", "").strip() == "Nữ"  # Nam trước (False < True)
                )
            )

            # Gộp lại theo đúng yêu cầu
            sorted_final.extend(selected_squad_members + remaining_sorted)

        # Ghi đè lại dataset
        del dataset[:]
        for row in sorted_final:
            dataset.append(row.values())

    # rules:
    # Assign rooms based on priority:
    # From lower floor to higher floor
    # From smaller room numbers first
    # Same gender in the same room
    # Same platoon/squad in the same room

    def save_instance(self, instance, *args, **kwargs):
        try:
            # Check if a student with the same name already exists.
            existing_instance = Student.objects.get(full_name=instance.full_name)
            instance.pk = existing_instance.pk  # Update rather than create a new entry.
        except ObjectDoesNotExist:
            pass  # No existing record found, treat it as a new instance.

        # Assign a room to the student if not already done.
        self.assign_student_room(instance)

        # Check if student has been assigned to a room.
        if instance.room_id is not None:
            # If the instance has a room, get the building from the room.
            # This assumes that your Student model has a foreign key 'room', and that Room has a 'building' field.
            building = instance.room.building

            # Ensure the list exists
            if not hasattr(self, 'buildings_list'):
                self.buildings_list = []

            # Append only if not already present
            if building not in self.buildings_list:
                self.buildings_list.append(building)

            # Save the instance.
            super().save_instance(instance, *args, **kwargs)
        else:
            RoomAssignmentCache.add_unassigned(instance)

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        """
        Perform bulk update after the actual import step.
        """
        flags = {
            "fill_empty_first": self.fill_empty_first,
            "fill_partial_first": self.fill_partial_first,
            "assign_direct": self.assign_direct,
        }

        self.process_arrange_students(**flags)

    def process_arrange_students(self, **flags):
        if flags["assign_direct"] is not True:
            BuildingUtils.update_building_under_occupied()
            # RoomAssignmentHelper.move_oversize_squad_to_last()
            RoomAssignmentHelper.merge_students_before_saving()
            if flags["fill_partial_first"] is not None and flags["fill_empty_first"] is False:
                RoomAssignmentHelper.fill_student_to_room_after_merge(selected_building_name=self.selected_buildings)
            else:
                RoomAssignmentHelper.fill_student_to_room_after_merge(self.dict_last_room, self.selected_buildings)
            StudentUtils.handle_filling_student_across_building()
        if len(self.buildings_list) >= 2:
            # StudentUtils.handle_mixed_squad_with_same_platoon()
            StudentUtils.fill_empty_rooms_in_dest_from_source()
            RoomAssignmentHelper.arrange_students_within_building()
        BuildingUtils.unlock_building_with_empty_room()
        RoomAssignmentHelper.lock_under_occupied_rooms()

    def assign_student_room(self, instance):
        """Determine and apply the best strategy for assigning a room."""

        # Extract required attributes
        selected_building_name = self._get_selected_building_name()
        room_code, gender, platoon, squad, building = RoomAssignmentHelper._extract_instance_details(instance)

        # Get flags
        flags = self._get_strategy_flags()

        #  Step 1: Select the best strategy
        strategy_method, strategy_args, strategy_kwargs = self._select_strategy(
            instance, building, room_code, selected_building_name, gender, platoon, squad, **flags
        )

        #  Step 2: Execute the chosen strategy
        strategy_method(instance, *strategy_args, **strategy_kwargs)

    def _get_selected_building_name(self):
        """Extract the selected building name from different formats."""
        selected_building = getattr(self, "selected_buildings", None)

        if isinstance(selected_building, QuerySet):
            return selected_building.values_list("name", flat=True).first()
        elif isinstance(selected_building, Building):
            return selected_building.name
        return None

    def _get_strategy_flags(self):
        """Retrieve boolean strategy flags."""
        return {
            "fill_empty_first": getattr(self, "fill_empty_first", None),
            "fill_partial_first": getattr(self, "fill_partial_first", None)
        }

    def _select_strategy(self, instance, building, room_code, selected_building_name, *args, **flags):
        """
        Select the best strategy based on available data and return required arguments.
        """

        if building is not None and room_code is not None:
            self.assign_direct = True
            return RoomAssignmentHelper.assign_room_directly, (building, room_code), {}

        elif building is not None:
            return RoomAssignmentHelper.assign_room_in_building, (building,), flags

        elif selected_building_name is not None:
            return RoomAssignmentHelper.assign_room_by_selected_building, (selected_building_name,), flags

        else:
            return RoomAssignmentHelper.assign_room_by_priority, (), flags


class RoomResource(BaseResource):
    class Meta:
        model = Room
        store_instance = True
        import_id_fields = ("id",)
        export_order = (
            "building",
            "floor",
            "room_code",
            "capacity",
            "note",
            "is_lock",
            "is_temporary_lock"
        )
        export_fields = (
            "building",
            "floor",
            "room_code",
            "capacity",
            "note",
            "is_lock",
            "is_temporary_lock"
        )

    building = fields.Field(
        attribute="building",
        column_name="Tòa nhà"
    )

    floor = fields.Field(
        attribute="floor",
        column_name="Tầng",
    )

    room_code = fields.Field(
        attribute="room_code",
        column_name="Mã phòng"
    )

    note = fields.Field(
        attribute="note",
        column_name="Ghi chú"
    )

    capacity = fields.Field(
        attribute="capacity",
        column_name="Sức chứa"
    )

    is_lock = fields.Field(
        attribute="is_lock",
        column_name="Khóa cố định"
    )

    is_temporary_lock = fields.Field(
        attribute="is_temporary_lock",
        column_name="Khóa tạm thời"
    )

    def dehydrate_building(self, instance):
        try:
            return instance.building.name
        except Exception as e:
            return "N/A"

    def dehydrate_is_lock(self, instance):
        try:
            return "Khóa" if instance.is_lock else "Không khóa"
        except Exception as e:
            return "Không xác định"

    def save_instance(self, instance, *args, **kwargs):
        room_code = getattr(instance, "room_code", "").strip()
        building_name = getattr(instance, "building", "").strip()

        if not building_name:
            raise Exception("Không thể xác định tòa nhà cho phòng.")

        try:
            building = Building.objects.get(name=building_name)
        except Building.DoesNotExist:
            raise Exception(f"Tòa nhà '{building_name}' không tồn tại.")

        if room_code:
            try:
                instance = Room.objects.get(building=building, room_code=room_code, is_lock=False)
            except Room.DoesNotExist:
                raise Exception(f"Phòng '{room_code}' không tồn tại trong tòa nhà '{building_name}'.")

        super().save_instance(instance, *args, **kwargs)


class BuildingResource(BaseResource):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.new_buidlings = set()

    class Meta:
        model = Building
        store_instance = True
        import_id_fields = ("id",)

        export_order = (
            "name",
            "number_of_floors",
            "number_of_room_each_floor",
            "capacity_each_room",
            "female_priority",
            "male_priority"
        )
        export_fields = (
            "name",
            "number_of_floors",
            "number_of_room_each_floor",
            "capacity_each_room",
            "female_priority",
            "male_priority"
        )

    name = fields.Field(
        attribute="name",
        column_name="Tên tòa nhà",
    )

    number_of_floors = fields.Field(
        attribute="number_of_floors",
        column_name="Số tầng"
    )

    number_of_room_each_floor = fields.Field(
        attribute="number_of_room_each_floor",
        column_name="Số phòng mỗi tầng"
    )

    capacity_each_room = fields.Field(
        attribute="capacity_each_room",
        column_name="Sức chứa mỗi phòng"
    )

    male_priority = fields.Field(
        attribute="male_priority",
        column_name="Độ ưu tiên cho nữ"
    )

    female_priority = fields.Field(
        attribute="female_priority",
        column_name="Độ ưu tiên cho nam"
    )

    def dehydrate_building(self, instance):
        try:
            return instance.name
        except Exception as e:
            return "N/A"

    def save_instance(self, instance, *args, **kwargs):
        building_name = getattr(instance, "name", "")
        male_priority = int(getattr(instance, "male_priority", 0))
        female_priority = int(getattr(instance, "female_priority", 0))
        number_of_floors = int(getattr(instance, "number_of_floors", None))
        number_of_room_each_floor = int(getattr(instance, "number_of_room_each_floor", None))
        capacity_each_room = int(getattr(instance, "capacity_each_room", None))

        if not building_name:
            raise ValueError("Tên tòa nhà không hợp lệ.")

        if not number_of_room_each_floor:
            raise ValueError("number_of_room_each_floor is none")

        if not capacity_each_room:
            raise ValueError("capacity_each_room is none")

        try:
            # Try to get the existing building
            building = Building.objects.get(name=building_name)
        except ObjectDoesNotExist:
            if number_of_floors is None:
                raise ValueError("Số tầng của tòa nhà là bắt buộc.")

            building = Building(
                name=building_name,
                number_of_floors=number_of_floors,
                number_of_room_each_floor=number_of_room_each_floor,
                capacity_each_room=capacity_each_room,
                male_priority=male_priority,
                female_priority=female_priority
            )
            try:
                building.save()
            except IntegrityError as e:
                raise ValueError(f"Lỗi khi lưu tòa nhà: {str(e)}")

        instance = building
        self.new_buidlings.add(instance)
        super().save_instance(instance, *args, **kwargs)

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        """
        Perform bulk update after the actual import step.
        """
        # Ensure new buildings exist and we are not in dry-run mode
        if hasattr(self, 'new_buildings') and self.new_buildings and not dry_run:
            # Convert set to list (optional, just for safety)
            new_buildings = list(self.new_buildings)

            # Call function to create floors and rooms for newly imported buildings
            for new_building in new_buildings:
                create_building_floors_and_rooms(new_building)
