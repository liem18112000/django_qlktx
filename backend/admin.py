from django.contrib import admin
from import_export.admin import ImportExportModelAdmin, ExportActionModelAdmin

from backend.models import Building, Room, Student


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
        "is_lock"
    )

    list_filter = ("building", "floor", "capacity", "is_lock")
    search_fields = ("room_code",)


@admin.register(Student)
class StudentAdmin(BaseAdmin):
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
