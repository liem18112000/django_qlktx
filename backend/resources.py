from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from backend.constants import Gender
from backend.models import Student, Room, Building


class StudentResource(resources.ModelResource):
    class Meta:
        model = Student
        store_instance = True
        import_id_fields = ("id",)
        # exclude = ("id",)
        export_order = (
            "building",
            "room",
            "full_name",
            "gender",
            "platoon",
            "squad",
            "position",
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

    def save_instance(self, instance, *args, **kwargs):
        room = str(getattr(instance, 'room_code', None))
        building = getattr(instance, "building", None)
        gender = getattr(instance, "gender", None)
        if building and building != "None" and building.strip() != "":
            if room and room != "None" and room.strip() != "":
                try:
                    instance.room = Room.objects.get(
                        building__name=building,
                        room_code=room,
                        is_lock=False
                    )
                except Room.DoesNotExist:
                    raise Exception("Phòng không tồn tại")
            else:
                instance.room = self._get_available_room(building, gender)
        else:
            has_room = False
            for building in Building.objects.all():
                try:
                    instance.room = self._get_available_room(building, gender)
                    has_room = True
                except:
                    pass
            if not has_room:
                raise Exception("Không còn phòng trong tòa nhà")
        super().save_instance(instance, *args, **kwargs)

    def _get_available_room(self, building, _gender):
        available_rooms = Room.objects.filter(building__name=building, is_lock=False).all()
        for room in available_rooms:
            student_room = Student.objects.filter(room=room)
            gender = student_room.first().gender
            if room.capacity > Student.objects.filter(room=room).count() and gender == _gender:
                return room
        raise Exception("Không còn phòng trong tòa nhà")
