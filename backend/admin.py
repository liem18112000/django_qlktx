from io import BytesIO

import openpyxl
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import render, redirect
from django.urls import reverse
from django_admin_action_forms import action_with_form
from import_export.admin import ImportExportModelAdmin, ExportActionModelAdmin
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter

from backend.form import StudentExportForm, RoomExportForm, BuildingExportForm, StudentImportForm, \
    SetBuildingForArrange
from backend.helper import RoomAssignmentHelper
from backend.models import Building, Room, Student, CustomUser, Platoon, Floor
from backend.resources import StudentResource, RoomResource, BuildingResource


class BaseAdmin(ImportExportModelAdmin, ExportActionModelAdmin, admin.ModelAdmin):
    list_per_page = 10

    def get_export_data(self, file_format, queryset, request=None, **kwargs):
        # Get raw export data from django-import-export
        blob = super().get_export_data(file_format, queryset, request=request, **kwargs)

        # Only modify if exporting to XLSX
        if file_format.get_title().lower() != "xlsx":
            return blob

        # Load workbook from exported data
        workbook_data = BytesIO(blob)
        wb = openpyxl.load_workbook(workbook_data)
        ws = wb.active  # Get the active sheet

        # Auto-fit column width
        for col_idx, col_cells in enumerate(ws.columns, start=1):  # Iterate through columns
            max_length = 0
            for cell in col_cells:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[get_column_letter(col_idx)].width = max_length + 2  # Add padding

        # Auto-fit row height based on content
        for row in ws.iter_rows():
            max_height = 15  # Default minimum height
            for cell in row:
                if cell.value:
                    lines = str(cell.value).count("\n") + 1  # Count line breaks
                    max_height = max(max_height, lines * 15)  # Set height based on lines
            ws.row_dimensions[row[0].row].height = max_height

        # Apply borders to all cells
        border_style = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        for row in ws.iter_rows():
            for cell in row:
                cell.border = border_style

        # Save modified workbook
        output = BytesIO()
        wb.save(output)
        output.seek(0)  # Ensure pointer is at the beginning
        return output.getvalue()


@admin.register(Building)
class BuildingAdmin(BaseAdmin):
    resource_classes = [BuildingResource]
    export_form_class = BuildingExportForm
    list_display = (
        "name",
        "number_of_floors",
        "number_of_room_each_floor",
        "capacity_each_room",
        "get_reserved_count",
        "female_priority",
        "male_priority"
    )

    list_filter = ("number_of_floors", "number_of_room_each_floor", "capacity_each_room")
    search_fields = ("name",)

    @admin.display(description='Số lượng chỗ đã sắp xếp')
    def get_reserved_count(self, obj):
        total = 0
        student_count = 0
        for room in Room.objects.filter(building=obj).all():
            student_count += Student.objects.filter(room=room).count()
            if not room.is_lock and not room.is_temporary_lock:
                total += room.capacity
        return f"{student_count}/{total}"

    readonly_fields = ('get_reserved_count',)

    def has_add_permission(self, request, obj=None):
        if obj and not request.user.can_manage_building(obj):
            return False
        return True

    def has_change_permission(self, request, obj=None):
        if obj and not request.user.can_manage_building(obj):
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if obj and not request.user.can_manage_building(obj):
            return False
        return True


@admin.register(Room)
class RoomAdmin(BaseAdmin):
    resource_classes = [RoomResource]
    export_form_class = RoomExportForm

    list_display = (
        "room_code",
        "building",
        "floor",
        "capacity",
        "reserved",
        "note",
        "is_lock",
        "is_temporary_lock"
    )

    list_filter = ("building", "floor", "capacity", "is_lock", "is_temporary_lock")
    search_fields = ("room_code",)

    actions = ["lock_rooms", "unlock_rooms", "temporary_lock_rooms", "temporary_unlock_rooms"]  # Add custom actions

    @admin.action(description="Khóa cố định cho các phòng đã chọn")
    def lock_rooms(self, request, queryset):
        """Set is_lock = True for selected rooms"""
        queryset.update(is_lock=True)

    @admin.action(description="Mở khóa cố định cho các phòng đã chọn")
    def unlock_rooms(self, request, queryset):
        """Set is_lock = False for selected rooms"""
        queryset.update(is_lock=False)

    @admin.action(description="Khóa tạm thời cho các phòng đã chọn")
    def temporary_lock_rooms(self, request, queryset):
        """Set is_lock = True for selected rooms"""
        queryset.update(is_temporary_lock=True)

    @admin.action(description="Mở khóa tạm thời cho các phòng đã chọn")
    def temporary_unlock_rooms(self, request, queryset):
        """Set is_lock = False for selected rooms"""
        queryset.update(is_temporary_lock=False)

    @admin.display(description='Đã chứa')
    def reserved(self, obj):
        return f"{Student.objects.filter(room=obj).count()}/{obj.capacity}"

    @admin.display(description="Ghi chú")
    def note(self, obj):
        # Get the first student in the room
        first_student = Student.objects.filter(room=obj).select_related("platoon").first()

        # Check if there's a student assigned
        if not first_student or not first_student.platoon:
            return "Không có"

        # Get the platoon name
        platoon_name = first_student.platoon.name
        students_count = Student.objects.filter(room=obj).count()

        return f"{platoon_name} - {students_count} học viên"

    def has_add_permission(self, request, obj=None):
        if obj and not request.user.can_manage_room(obj):
            return False
        return True

    def has_change_permission(self, request, obj=None):
        if obj and not request.user.can_manage_room(obj):
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if obj and not request.user.can_manage_room(obj):
            return False
        return True


@admin.register(Student)
class StudentAdmin(BaseAdmin):
    resource_classes = [StudentResource]
    export_form_class = StudentExportForm
    import_form_class = StudentImportForm
    list_display = (
        "full_name",
        "room",
        "platoon",
        "squad",
        "position",
        "phone_number",
        "headmaster"
    )

    list_filter = ("room", "platoon", "squad", "position", "phone_number", "headmaster", "gender")
    search_fields = ["full_name", ]
    search_help_text = "Search by full name. Type at least 3 characters."
    actions = ["arrange_student_to_building_action"]
    autocomplete_fields = ["platoon", "room"]

    @action_with_form(
        SetBuildingForArrange,
        description="sắp xếp học viên đã chọn",
    )
    def arrange_student_to_building_action(self, request, queryset, data):
        """Assign students to buildings and floors based on gender selection or automatic priority."""

        general_building, general_floor = data.get("building"), data.get("floor")

        flags = {
            "fill_empty_first": data.get("fill_empty_first", False),
            "fill_partial_first": data.get("fill_partial_first", True)
        }

        if isinstance(general_floor, Floor):
            general_floor_number = general_floor.floor_number
        else:
            general_floor_number = None  # Default value if it's not a Floor instance

        gender_1, building_1, floor_1 = data.get("gender_1"), data.get("building_1"), data.get("floor_1")
        gender_2, building_2, floor_2 = data.get("gender_2"), data.get("building_2"), data.get("floor_2")

        if isinstance(floor_1, Floor):
            floor_number_1 = floor_1.floor_number
        else:
            floor_number_1 = None

        if isinstance(floor_2, Floor):
            floor_number_2 = floor_2.floor_number
        else:
            floor_number_2 = None

        for student in queryset:
            student_gender = student.gender.strip().lower()
            gender_assignment_1 = (gender_1 and student_gender == gender_1.strip().lower() and building_1 and
                                   floor_number_1)
            gender_assignment_2 = (gender_2 and student_gender == gender_2.strip().lower() and building_2 and
                                   floor_number_2)

            if general_building and general_floor_number:
                RoomAssignmentHelper.assign_room_by_building_and_floor(student, general_building, general_floor_number,
                                                                       **flags)

            elif gender_assignment_1:
                RoomAssignmentHelper.assign_room_by_building_and_floor(student, building_1, floor_number_1, **flags)

            elif gender_assignment_2:
                RoomAssignmentHelper.assign_room_by_building_and_floor(student, building_2, floor_number_2, **flags)

            else:
                RoomAssignmentHelper.assign_room_by_priority(student, **flags)

            student.save()

        if flags.get("fill_empty_first") is False:
            RoomAssignmentHelper.merge_students_before_saving()
            RoomAssignmentHelper.arrange_students_within_building()

        self.message_user(request, f"{queryset.count()} học viên đã được sắp xếp phòng.")

    def get_import_data_kwargs(self, request, *args, **kwargs):
        """
        Override to pass the selected building from the import form.
        """
        print("kwargs", kwargs)
        data_kwargs = super().get_import_data_kwargs(request, *args, **kwargs)
        form = kwargs.get("form")
        if form:
            data_kwargs["selected_building"] = form.cleaned_data.get("building")
            data_kwargs["fill_empty_first"] = form.cleaned_data.get("fill_empty_first")
            data_kwargs["fill_partial_first"] = form.cleaned_data.get("fill_partial_first")
        return data_kwargs

    def has_add_permission(self, request, obj=None):
        if obj and not request.user.can_manage_student(obj):
            return False
        return True

    def has_change_permission(self, request, obj=None):
        if obj and not request.user.can_manage_student(obj):
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if obj and not request.user.can_manage_student(obj):
            return False
        return True


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Make CustomUserAdmin behave like Django's built-in auth UserAdmin.
    """
    model = CustomUser

    # Define the fields displayed in Django Admin
    list_display = ("username", "email", "role", "is_staff", "is_superuser")
    list_filter = ("role", "is_staff", "is_superuser", "platoon", "floors", "buildings")
    search_fields = ("username", "email")

    # Define fieldsets (like the default auth UserAdmin)
    fieldsets = (
        ("Thông tin chung", {"fields": ("username", "password")}),
        ("Thông tin cá nhân", {"fields": ("first_name", "last_name", "email", "role")}),
        ("Các quyền", {
            "fields": ("is_active", "is_staff", "is_superuser", ("groups", "user_permissions")),
            "classes": ("collapse", "wide", "custom-permissions-class"),  # Add classes here
        }),
        ("Quản lý", {"fields": ("platoon", "floors", "buildings")}),
    )

    # Define add_fieldsets for user creation
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "role", "platoon", "floors", "buildings", "password1", "password2"),
        }),
    )

    ordering = ("username",)


@admin.register(Platoon)
class PlatoonAdmin(BaseAdmin):
    list_display = (
        "name",
        "num_member",
    )

    list_filter = ("name",)
    search_fields = ("name",)

    @admin.display(description="Số học viên")
    def num_member(self, obj):
        students = Student.objects.filter(platoon=obj).count()

        return f"{students} học viên"


# Custom Admin Dashboard
def custom_admin_dashboard(request):
    buildings = Building.objects.all()  # Fetch all Building objects

    # Ensure URLs are correctly reversed
    try:
        building_changelist_url = reverse("admin:backend_building_changelist")
        room_changelist_url = reverse("admin:backend_room_changelist")
        student_changelist_url = reverse("admin:backend_student_changelist")
    except Exception as e:
        print(f"Error reversing URL: {e}")
        building_changelist_url = "#"
        room_changelist_url = "#"
        student_changelist_url = "#"

    context = admin.site.each_context(request)  # Default admin context
    context["buildings"] = buildings
    context["building_changelist_url"] = building_changelist_url
    context["room_changelist_url"] = room_changelist_url
    context["student_changelist_url"] = student_changelist_url

    return render(request, "admin/custom_dashboard.html", context)


# Custom Admin Site
class CustomAdminSite(admin.AdminSite):
    index_template = "admin/custom_dashboard.html"

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        buildings = Building.objects.all()
        data = []
        total_room = 0
        total_space = 0
        occupied_space = 0
        for index, building in enumerate(buildings):
            locked_room = Room.objects.filter(building=building, is_lock=True).count()
            room_count = building.number_of_room_each_floor * building.number_of_floors - locked_room
            all_space_count = room_count * building.capacity_each_room
            occupied_count = 0
            for room in Room.objects.filter(building=building):
                occupied_count += Student.objects.filter(room=room).count()
            unoccupied_count = all_space_count - occupied_count
            item = {
                "id": index + 1,
                "name": building.name,
                "room_count": room_count,
                "all_space_count": all_space_count,
                "occupied_count": occupied_count,
                "unoccupied_count": unoccupied_count,
                "note": ""
            }
            total_room = total_room + room_count
            total_space = total_space + all_space_count
            occupied_space = occupied_space + occupied_count
            data.append(item)

        extra_context["data"] = data
        extra_context["total_room"] = total_room
        extra_context["total_space"] = total_space
        extra_context["occupied_space"] = occupied_space
        extra_context["unoccupied_space"] = total_space - occupied_space
        return super().index(request, extra_context=extra_context)


# Create a new CustomAdminSite instance
custom_admin_site = CustomAdminSite(name="custom_admin")

# Copy all existing model registrations from admin.site to custom_admin_site
for model, model_admin in admin.site._registry.items():
    if model not in custom_admin_site._registry:  # Prevent duplicate registration
        custom_admin_site.register(model, model_admin.__class__)  # Keep existing admin settings

# Ensure Django uses the custom admin site
admin.site = custom_admin_site
