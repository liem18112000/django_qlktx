import logging
from collections import defaultdict
from sqlite3 import IntegrityError

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet, Count, F
from import_export import fields, resources
from tablib import Dataset

from backend.helper import RoomAssignmentHelper
from backend.models import Student, Room, Building, Platoon
from backend.signals import create_building_floors_and_rooms


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
        self.done_import = None
        self.assign_direct = None
        self.fill_partial_first = None
        self.selected_buildings = None
        self.fill_empty_first = None
        self.new_squad = defaultdict(list)  # Temporary storage for batch processing
        self.instances_to_save = []  # Store instances here
        self.processed_instances = 0  # Track how many instances have been processed
        self.total_instances = 0  # Track total students in the import

    class Meta:
        model = Student
        use_bulk = True
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

        if self.total_instances == 0:
            self.total_instances = len(dataset)  # Get total number of students

        print("Total Instances:", self.total_instances)

        # Convert dataset to a list of dictionaries for easier sorting
        data_list = [dict(zip(dataset.headers, row)) for row in dataset]

        # Sort students by:
        # 1. Platoon (Trung đội)
        # 2. Squad number (Tiểu đội) → Convert to integer for correct sorting
        # 3. Gender (Giới tính) → Ensure "Nữ" comes last within each platoon
        data_list.sort(
            key=lambda x: (
                x.get("Trung đội ", "").strip(),  # Sort by Platoon
                x.get("Giới tính", "").strip() == "Nữ",  # Ensure "Nữ" goes last (False for "Nữ", True for "Nam")
                int(x.get("Tiểu đội", 0))  # Sort by Squad Number
            )
        )

        # Clear existing dataset and re-add sorted data
        del dataset[:]  # This removes all rows while keeping headers
        for row in data_list:
            dataset.append(row.values())

        print("Sorted Dataset:\n", dataset)

    # rules:
    # Assign rooms based on priority:
    # From lower floor to higher floor
    # From smaller room numbers first
    # Same gender in the same room
    # Same platoon/squad in the same room

    def save_instance(self, instance, *args, **kwargs):

        self.assign_student_room(instance)

        instance.save()
        # super().save_instance(instance, *args, **kwargs)  # Save student first

        self.processed_instances += 1
        if self.processed_instances == self.total_instances:
            self.done_import = True

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        """
        Perform bulk update after the actual import step.
        """
        if self.assign_direct is not True:
            RoomAssignmentHelper.merge_students_before_saving()
            RoomAssignmentHelper.arrange_students_within_building()

    def assign_student_room(self, instance):
        """Determine and apply the best strategy for assigning a room."""

        # Extract required attributes
        selected_building_name = self._get_selected_building_name()
        room_code, gender, platoon, squad, building = self._extract_instance_details(instance)

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

    def _extract_instance_details(self, instance):
        """Extract and preprocess instance attributes."""
        room_code = getattr(instance, "room_code", None)
        if isinstance(room_code, int):
            room_code = str(room_code)

        gender = getattr(instance, "gender", None)
        platoon_name = getattr(instance, "platoon", None)
        squad = getattr(instance, "squad", None)
        building = getattr(instance, "building", None)
        if isinstance(building, str):
            building = Building.objects.get(name=building)

        # Get Platoon object safely
        platoon = Platoon.objects.get(name=platoon_name) if platoon_name else None

        return room_code, gender, platoon, squad, building

    def _get_strategy_flags(self):
        """Retrieve boolean strategy flags."""
        return {
            "fill_empty_first": getattr(self, "fill_empty_first", None),
            "fill_partial_first": getattr(self, "fill_partial_first", None)
        }

    def _select_strategy(self, instance, building, room_code, selected_building_name, gender, platoon, squad, **flags):
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
        number_of_floors = int(getattr(instance,"number_of_floors", None))
        number_of_room_each_floor = int(getattr(instance,"number_of_room_each_floor", None))
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
