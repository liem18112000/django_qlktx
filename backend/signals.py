import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

from backend.models import Building, Room

User = get_user_model()


@receiver(post_save, sender=Building)
@transaction.atomic
def building_post_save(sender, instance, created, **kwargs):
    if created:
        number_of_floors = instance.number_of_floors
        number_of_room_each_floor = instance.number_of_room_each_floor
        capacity_each_room = instance.capacity_each_room
        if number_of_room_each_floor > 0 and number_of_floors > 0:
            for i in range(number_of_floors):
                for j in range(number_of_room_each_floor):
                    room_code = f"{str(i + 1)}0{str(j + 1)}" if j + 1 < 10 else f"{str(i + 1)}{str(j + 1)}"
                    Room.objects.create(
                        building=instance,
                        room_code=room_code,
                        floor=i + 1,
                        capacity=capacity_each_room
                    )

