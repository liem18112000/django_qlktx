from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models

from backend.constants import Gender


# Create your models here.
class Building(models.Model):
    class Meta:
        verbose_name = "Tòa nhà"
        verbose_name_plural = "Tòa nhà"

    # Building name (Tên tòa nhà)
    name = models.CharField("Tên tòa nhà", max_length=255)

    # Number of floors (Số lượng tầng)
    number_of_floors = models.PositiveSmallIntegerField("Số lượng tầng")

    number_of_room_each_floor = models.PositiveSmallIntegerField("Số lượng phòng mỗi tầng", default=10)

    capacity_each_room = models.PositiveSmallIntegerField("Số lượng học viên mỗi phòng", default=10)

    female_priority = models.PositiveSmallIntegerField(default=0, verbose_name="Độ ưu tiên (dành cho xếp ưu tiên kí "
                                                                               "túc xá nữ)")

    male_priority = models.PositiveSmallIntegerField(default=0, verbose_name="Độ ưu tiên (dành cho xếp ưu tiên kí "
                                                                             "túc xá nam)")
    under_occupied = models.BooleanField("có học sinh ở tất cả phòng", default=False)

    def __str__(self):
        return self.name


class Room(models.Model):
    class Meta:
        verbose_name = "Phòng"
        verbose_name_plural = "Phòng"
        unique_together = (("building", "room_code"),)

    # Building name (Tòa nhà)
    building = models.ForeignKey(Building, verbose_name="Tòa nhà", on_delete=models.CASCADE)

    # Floor (Tầng)
    floor = models.ForeignKey("Floor", verbose_name="Tầng", on_delete=models.CASCADE)

    # Room code (Mã phòng)
    room_code = models.CharField("Mã phòng", max_length=20)

    # Capacity (Sức chứa)
    capacity = models.PositiveSmallIntegerField("Sức chứa", default=10)

    # Is Lock (Khóa cố định)
    is_lock = models.BooleanField("Khóa phòng cố định", default=False)

    # Is_temporary_lock (Khóa tạm thời)
    is_temporary_lock = models.BooleanField("Khóa phòng tạm thời", default=False)

    # Is_lock_to_move (Khóa học sinh bị dời ra ngoài)
    is_lock_to_move = models.BooleanField("Khóa học sinh bị dời ra ngoài ", default=False)

    def __str__(self):
        return f"{self.building}-{self.room_code}"


class Student(models.Model):
    class Meta:
        verbose_name = "Học viên"
        verbose_name_plural = "Học viên"

    # Full name of the student
    full_name = models.CharField("Họ và tên", max_length=255)

    # Gender of student
    gender = models.TextField("Giới tính", max_length=4, choices=Gender.choices, default=Gender.FEMALE)

    # Platoon (Trung đội)
    platoon = models.ForeignKey("Platoon", on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name="Trung đội")

    # Squad (Tiểu đội)
    squad = models.CharField("Tiểu đội", max_length=50)

    # Position (Chức vụ)
    position = models.CharField("Chức vụ", max_length=50, null=True)

    # Phone Number (Số điện thoại)
    phone_number = models.CharField("Số điện thoại", max_length=20, blank=True, null=True)

    # Headmaster (Chủ nhiệm)
    headmaster = models.CharField("Chủ nhiệm Trung Đội", max_length=50)

    # Room (Phòng)
    room = models.ForeignKey(Room, verbose_name="Phòng", on_delete=models.CASCADE)

    def __str__(self):
        return self.full_name


class Platoon(models.Model):
    class Meta:
        verbose_name = "Trung đội"
        verbose_name_plural = "Trung đội"

    name = models.CharField(max_length=100, verbose_name="Tên Trung đội")

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    """
    Custom User model extending AbstractUser to include platoon and role attributes.
    """

    class Meta:
        verbose_name = "Người dùng"
        verbose_name_plural = "Người dùng"

    ROLE_CHOICES = [
        ("Student", "Học viên"),
        ("Headmaster", "Chủ nhiệm trung đội"),
        ("Admin", "Quản lý phần mềm"),
        ("Room Manager", "Lãnh đạo phòng")
    ]

    role = models.CharField(max_length=256, choices=ROLE_CHOICES, default="Học viên", verbose_name="Vai trò")
    floors = models.ManyToManyField("Floor", blank=True, verbose_name="Các tầng quản lý")
    platoon = models.ForeignKey("Platoon", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Trung đội")
    buildings = models.ManyToManyField("Building", blank=True, verbose_name="Các tòa nhà quản lý")

    # Fix conflicts by overriding related_name
    groups = models.ManyToManyField(Group, related_name="custom_user_groups", blank=True, verbose_name="Nhóm")
    user_permissions = models.ManyToManyField(Permission, related_name="custom_user_permissions", blank=True,
                                              verbose_name="Quyền người dùng")

    def has_permission(self, role_permissions):
        """
        Generic permission checker.
        :param role_permissions: Dict of role-specific permissions.
        :return: Boolean indicating whether the user has permission.
        """
        return role_permissions.get(self.role, False)

    def can_manage_student(self, student):
        """ Headmaster can manage students in the same platoon, Admin can manage all """
        return self.has_permission({"Admin": True, "Headmaster": self.platoon == student.platoon, "Room Manager": True})

    def can_manage_platoon(self, platoon):
        """ Headmaster can manage their own platoon, Admin can manage all """
        return self.has_permission({"Admin": True, "Headmaster": self.platoon == platoon, "Room Manager": True})

    def can_manage_building(self, building):
        """ Only Admin can manage buildings """
        return self.has_permission({"Admin": True})

    def can_manage_floor(self, floor):
        """ Room Manager can manage floors, Admin can manage all """
        return self.has_permission({"Admin": True, "Room Manager": self.floors.filter(id=floor.id).exists()})

    def can_manage_room(self, room):
        """ Room Manager can manage rooms, Admin can manage all """
        return self.has_permission({"Admin": True, "Room Manager": True})


class Floor(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="floors", verbose_name="Tòa nhà")
    floor_number = models.PositiveSmallIntegerField(verbose_name="Tầng")
    rooms = models.ManyToManyField("Room", blank=True, related_name="floors", verbose_name="Phòng")

    class Meta:
        unique_together = ("building", "floor_number")  # Ensure unique floor numbers within a building

    def __str__(self):
        return f"Tòa {self.building.name} - Tầng {self.floor_number}"
