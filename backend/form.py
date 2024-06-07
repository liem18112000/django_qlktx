from django import forms
from import_export.forms import ExportForm

from backend.models import Room


class StudentExportForm(ExportForm):
    room = forms.ModelMultipleChoiceField(
        label="Phòng",
        queryset=Room.objects.all(),
        required=False,
    )
