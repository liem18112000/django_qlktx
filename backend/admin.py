from django.contrib import admin
from import_export.admin import ImportExportModelAdmin, ExportActionModelAdmin

from backend.form import StudentExportForm
from backend.models import Building, Room, Student
from backend.resources import StudentResource


class BaseAdmin(ImportExportModelAdmin, ExportActionModelAdmin):
    list_per_page = 10


@admin.register(Building)
class BuildingAdmin(BaseAdmin):
    list_display = (
        "name",
        "address",
        "number_of_floors",
        "number_of_room_each_floor",
        "capacity_each_room",
        "get_reserved_count",
        "priority",
    )

    list_filter = ("number_of_floors", "number_of_room_each_floor", "capacity_each_room")
    search_fields = ("name", "address")

    @admin.display(description='Số lượng chỗ đã sắp xếp')
    def get_reserved_count(self, obj):
        total = 0
        student_count = 0
        for room in Room.objects.filter(building=obj).all():
            student_count += Student.objects.filter(room=room).count()
            total += room.capacity
        return f"{student_count}/{total}"

    readonly_fields = ('get_reserved_count',)


@admin.register(Room)
class RoomAdmin(BaseAdmin):
    list_display = (
        "room_code",
        "building",
        "floor",
        "capacity",
        "reserved",
        "is_lock"
    )

    list_filter = ("building", "floor", "capacity", "is_lock")
    search_fields = ("room_code",)

    @admin.display(description='Đã chứa')
    def reserved(self, obj):
        return f"{Student.objects.filter(room=obj).count()}/{obj.capacity}"


@admin.register(Student)
class StudentAdmin(BaseAdmin):
    resource_classes = [StudentResource]
    export_form_class = StudentExportForm
    list_display = (
        "full_name",
        "room",
        "platoon",
        "squad",
        "position",
        "headmaster"
    )

    list_filter = ("room", "platoon", "squad", "position", "headmaster")
    search_fields = ("full_name",)
