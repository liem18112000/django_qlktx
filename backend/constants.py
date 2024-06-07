from django.db import models


class Gender(models.TextChoices):
    MALE = "Nam"
    FEMALE = "Nữ"
    OTHER = "Khác"
