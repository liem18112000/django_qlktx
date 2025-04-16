# Store role-specific permission sets as constants
from django.contrib.auth.models import Permission


ROLE_MODEL_PERMISSIONS = {
    "Admin": Permission.objects.values_list("codename", flat=True),  # all permissions
    "Headmaster": [
        "view_customuser",
        "view_student", "add_student", "change_student", "delete_student",
        "view_platoon", "add_platoon", "change_platoon", "delete_platoon",
    ],
    "Room Manager": [
        "view_building",
        "view_customuser",
        "view_floor", "add_floor", "change_floor", "delete_floor",
        "view_room", "add_room", "change_room", "delete_room",
        "view_student", "add_student", "change_student", "delete_student",
        "view_platoon", "add_platoon", "change_platoon", "delete_platoon",

    ],
    "Student": [
        "view_customuser"
    ]
}