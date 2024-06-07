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
    )

    list_filter = ("number_of_floors",)
    search_fields = ("name", "address")


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
