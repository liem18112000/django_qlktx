from django.db import models

from backend.constants import Gender


# Create your models here.
class Building(models.Model):
    class Meta:
        verbose_name = "Tòa nhà"
        verbose_name_plural = "Các tòa nhà"

    # Building name (Tên tòa nhà)
    name = models.CharField("Tên tòa nhà", max_length=255)

    # Building address (Địa chỉ)
    address = models.CharField("Địa chỉ", max_length=255)

    # Number of floors (Số lượng tầng)
    number_of_floors = models.PositiveSmallIntegerField("Số lượng tầng")

    number_of_room_each_floor = models.PositiveSmallIntegerField("Số lượng phòng mỗi tầng", default=10)

    def __str__(self):
        return self.name


class Room(models.Model):
    class Meta:
        verbose_name = "Phòng"
        verbose_name_plural = "Các phòng"
        unique_together = (("building", "room_code"),)

    # Building name (Tòa nhà)
    building = models.ForeignKey(Building, verbose_name="Tòa nhà", on_delete=models.CASCADE)

    # Floor number (Tầng)
    floor = models.PositiveSmallIntegerField("Tầng")

    # Room code (Mã phòng)
    room_code = models.CharField("Mã phòng", max_length=20)

    # Capacity (Sức chứa)
    capacity = models.PositiveSmallIntegerField("Sức chứa", default=10)

    # Is Lock (Khóa)
    is_lock = models.BooleanField("Khóa phòng", default=False)

    def __str__(self):
        return f"Phòng {self.room_code} tại Tòa nhà {self.building} (Lầu {self.floor})"


class Student(models.Model):
    class Meta:
        verbose_name = "Học viên"
        verbose_name_plural = "Các học viên"

    # Full name of the student
    full_name = models.CharField("Họ và tên", max_length=255)

    # Gender of student
    gender = models.TextField("Giới tính", max_length=4, choices=Gender.choices, default=Gender.MALE)

    # Platoon (Trung đội)
    platoon = models.CharField("Trung đội", max_length=50)

    # Squad (Tiểu đội)
    squad = models.CharField("Tiểu đội", max_length=50)

    # Position (Chức vụ)
    position = models.CharField("Chức vụ", max_length=50)

    # Headmaster (Chủ nhiệm)
    headmaster = models.CharField("Chủ nhiệm Trung Đội", max_length=50)

    # Room (Phòng)
    room = models.ForeignKey(Room, verbose_name="Phòng", on_delete=models.CASCADE)

    def __str__(self):
        return self.full_name
