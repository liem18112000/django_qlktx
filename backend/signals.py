from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from backend.helper import RoomAssignmentHelper
from backend.models import Room, Floor, Building, Student, CustomUser, Platoon
from backend.permissions_constants import ROLE_MODEL_PERMISSIONS


@receiver(pre_save, sender=Building)
def store_old_building_values(sender, instance, **kwargs):
    """Store old number_of_room_each_floor before update"""
    if instance.pk:  # Only for updates
        old_building = Building.objects.filter(pk=instance.pk).only('number_of_room_each_floor').first()
        if old_building:
            instance._old_number_of_room_each_floor = old_building.number_of_room_each_floor


@receiver(post_save, sender=Building)
@transaction.atomic
def building_post_save(sender, instance, created, **kwargs):
    if created:
        create_building_floors_and_rooms(instance)
    else:
        update_building_floors_and_rooms(instance)


def create_building_floors_and_rooms(building):
    """Creates floors and rooms when a new building is added."""
    number_of_floors = building.number_of_floors
    number_of_room_each_floor = building.number_of_room_each_floor
    capacity_each_room = building.capacity_each_room

    # Create Floors
    floors = [Floor(building=building, floor_number=i) for i in range(1, number_of_floors + 1)]
    created_floors = Floor.objects.bulk_create(floors)

    # Create Rooms and Assign to Floors
    room_mapping = {}
    rooms = []

    for floor in created_floors:
        room_mapping[floor] = []
        for j in range(1, number_of_room_each_floor + 1):
            room_code = f"{floor.floor_number}0{j}" if j < 10 else f"{floor.floor_number}{j}"
            room = Room(
                building=building,
                floor=floor,  # Fix: An assign floor
                room_code=room_code,
                capacity=capacity_each_room
            )
            rooms.append(room)
            room_mapping[floor].append(room)

    # Bulk create rooms
    created_rooms = Room.objects.bulk_create(rooms)

    # Assign rooms to floors (ManyToMany)
    room_iterator = iter(created_rooms)
    for floor, room_list in room_mapping.items():
        floor.rooms.set([next(room_iterator) for _ in room_list])


def update_building_floors_and_rooms(building):
    """Handles updates when the number of rooms per floor changes."""
    old_room_count = getattr(building, '_old_number_of_room_each_floor', 0)
    new_room_count = building.number_of_room_each_floor
    capacity_each_room = building.capacity_each_room

    if old_room_count == new_room_count:
        return  # No changes, so skip updates

    for floor in building.floors.all():
        remove_excess_rooms(floor, new_room_count)
        add_missing_rooms(floor, new_room_count, building, capacity_each_room)
        update_room_capacities(floor, capacity_each_room)


def remove_excess_rooms(floor, new_room_count):
    """Safely removes excess rooms by moving students first, and switching buildings if necessary."""
    existing_rooms = list(floor.rooms.all())

    if len(existing_rooms) > new_room_count:
        rooms_to_remove = existing_rooms[new_room_count:]

        for room in rooms_to_remove:
            students_in_room = Student.objects.filter(room=room)

            if students_in_room.exists():
                # Try to rearrange students in the same building first
                success = move_students_to_available_room(students_in_room, room)

                if not success:
                    # If no space in the same building, move to another building
                    success = move_students_to_another_building(students_in_room, room.building)

                    if not success:
                        print(f" Cannot delete room {room.room_code}, no available space in any building.")
                        continue  # Skip deleting this room

            # Recheck if the room is now empty before deletion
            if not Student.objects.filter(room=room).exists():
                floor.rooms.remove(room)  # Remove from ManyToMany
                room.delete()
            else:
                print(f" Room {room.room_code} was not deleted because students are still assigned.")


def move_students_to_available_room(students, room):
    """Tries to move students to another room within the same building."""
    for student in students:
        try:
            available_room = RoomAssignmentHelper.get_available_room(room.building, student.gender, student.platoon,
                                                                     student.squad)
            student.room = available_room
            student.save()  # Move student to new room
        except Exception as e:
            print(e)
            return False  # No space available in the same building

    return True  # Successfully moved all students


def move_students_to_another_building(students, current_building):
    """Finds another building with available rooms and moves students there."""
    for student in students:
        try:
            available_building = Building.objects.exclude(id=current_building.id).order_by(
                '-female_priority' if student.gender == "Nữ" else '-male_priority').first()

            if not available_building:
                return False  # No other buildings available

            available_room = RoomAssignmentHelper.get_available_room(available_building, student.gender,
                                                                     student.platoon, student.squad)
            student.room = available_room
            student.save()  # Move student to new building
        except Exception:
            return False  # No space in any other building

    return True  # Successfully moved all students


def add_missing_rooms(floor, new_room_count, building, capacity_each_room):
    """Adds new rooms if the new count is higher."""
    existing_count = floor.rooms.count()

    if existing_count < new_room_count:
        new_rooms = []
        for j in range(existing_count + 1, new_room_count + 1):
            room_code = f"{floor.floor_number}0{j}" if j < 10 else f"{floor.floor_number}{j}"
            new_rooms.append(
                Room(building=building, floor=floor, room_code=room_code, capacity=capacity_each_room)
            )

        # Bulk create and assign rooms
        created_rooms = Room.objects.bulk_create(new_rooms)
        floor.rooms.add(*created_rooms)


def update_room_capacities(floor, new_capacity):
    """Updates the capacity of all rooms in the floor."""
    Room.objects.filter(floor=floor).update(capacity=new_capacity)
