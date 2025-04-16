from django import forms
from django.utils.translation import gettext_lazy as _
from django_admin_action_forms import AdminActionForm
from import_export.forms import ExportForm, ImportForm

from backend.models import Room, Building, Floor


class StudentExportForm(ExportForm):
    room = forms.ModelMultipleChoiceField(
        label="Phòng",
        queryset=Room.objects.all(),
        required=False,
    )


class StudentImportForm(ImportForm):
    building = forms.ModelChoiceField(
        label="Tòa nhà",
        queryset=Building.objects.all(),
        required=False,
    )
    fill_empty_first = forms.BooleanField(
        label="Sắp xếp học viên lẻ vào phòng trống",
        required=False,
    )
    fill_partial_first = forms.BooleanField(
        label="Sắp xếp học viên lẻ vào phòng có học viên",
        required=False,
    )


class RoomExportForm(ExportForm):
    building = forms.ModelMultipleChoiceField(
        label="Tòa nhà",
        queryset=Building.objects.all(),
        required=False,
    )


class BuildingExportForm(ExportForm):
    pass


class SetBuildingForArrange(AdminActionForm):
    """
    Custom action form with optional gender-based room assignments.
    """

    building = forms.ModelChoiceField(
        label="Tòa nhà",
        queryset=Building.objects.all(),
        required=False,
    )

    floor = forms.ModelChoiceField(
        label="Tầng",
        queryset=Floor.objects.none(),
        required=False,
    )

    fill_empty_first = forms.BooleanField(
        label="Sắp xếp học viên vào phòng trống",
        required=False,
    )

    fill_partial_first = forms.BooleanField(
        label="Sắp xếp học viên vào phòng có học viên",
        initial=True,
        required=False,
    )

    gender_1 = forms.ChoiceField(
        label="Chọn",
        choices=[("", "------"), ("nam", "Nam")],
        required=False,
        initial="nam"
    )

    building_1 = forms.ModelChoiceField(
        label="Cho tòa nhà",
        queryset=Building.objects.all(),
        required=False,
    )

    floor_1 = forms.ModelChoiceField(
        label="Vào Tầng",
        queryset=Floor.objects.none(),
        required=False,
    )

    gender_2 = forms.ChoiceField(
        label="Chọn",
        choices=[("", "------"), ("nữ", "Nữ")],
        required=False,
        initial="nữ"
    )

    building_2 = forms.ModelChoiceField(
        label="Cho tòa nhà",
        queryset=Building.objects.all(),
        required=False,
    )

    floor_2 = forms.ModelChoiceField(
        label="Vào Tầng",
        queryset=Floor.objects.none(),
        required=False,
    )

    class Meta:
        list_object = True
        confirm_button_text = _("Xác nhận")
        cancel_button_text = _(" ")

        fieldsets = [
            ('Chung', {
                'fields': [
                    'building', "floor", "fill_empty_first", "fill_partial_first"
                ],
            }),
            ('Giới tính', {
                "classes": [""],
                'fields': [
                    ('gender_1', "building_1", "floor_1"),
                    ('gender_2', "building_2", "floor_2")
                ],
            }),
        ]

    def filter_floors(self, building_field, floor_field):
        """Helper function to dynamically filter floors based on the selected building."""
        if building_field in self.data:
            try:
                building_id = int(self.data.get(building_field))
                self.fields[floor_field].queryset = Floor.objects.filter(building_id=building_id)
            except (ValueError, TypeError):
                self.fields[floor_field].queryset = Floor.objects.none()
        else:
            self.fields[floor_field].queryset = Floor.objects.none()

    def __init__(self, *args, **kwargs):
        """Dynamically filter floors based on the selected building."""
        super().__init__(*args, **kwargs)

        self.filter_floors("building", "floor")
        self.filter_floors("building_1", "floor_1")
        self.filter_floors("building_2", "floor_2")

    class Media:
        js = (
            "admin/js/vendor/jquery/jquery.js",
            "qlktx/js/admin_action.js",
        )
