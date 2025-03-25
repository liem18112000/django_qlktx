import logging
from collections import Counter
from itertools import cycle

from django.db import models
from django.db.models import Count, F

from .models import Room, Student, Building, Floor, Platoon


class RoomAssignmentHelper:
    """
    Helper class to manage room assignments for students.
    """

    @staticmethod
    def assign_room_directly(instance, building, room_code):
        """Assign the student directly to a specific room in a building."""
        try:
            instance.room = Room.objects.get(
                building=building,
                room_code=room_code,
                is_lock=False,
                is_temporary_lock=False,
            )
        except Room.DoesNotExist:
            raise Exception("Phòng không tồn tại trong tòa nhà được chỉ định.")

    @staticmethod
    def assign_room_in_building(instance, building, **flags):
        """Find an available room inside the specified building."""
        instance.room = RoomAssignmentHelper.get_available_room(building, instance.gender, instance.platoon,
                                                                instance.squad, **flags)

    @staticmethod
    def assign_room_by_priority(instance, **flags):
        """Assign a building based on gender priority."""
        gender = instance.gender
        buildings = Building.objects.all().order_by(
            '-female_priority' if gender == "Nữ" else '-male_priority'
        )

        for building in buildings:
            try:
                instance.room = RoomAssignmentHelper.get_available_room(building, gender, instance.platoon,
                                                                        instance.squad, **flags)
                return
            except Exception as e:
                pass  # Try the next building

        raise Exception("Không còn phòng phù hợp trong tất cả các tòa nhà.")

    @staticmethod
    def assign_room_by_selected_building(instance, selected_building_name=None, **flags):
        """Assign student to an available room in the selected building."""
        if not selected_building_name:
            raise Exception("Tên tòa nhà không hợp lệ.")

        building = Building.objects.filter(name=selected_building_name).first()

        if not building:
            raise Exception(f"Tòa nhà '{selected_building_name}' không tồn tại.")

        instance.room = RoomAssignmentHelper.get_available_room(building, instance.gender, instance.platoon,
                                                                instance.squad, **flags)

    @staticmethod
    def get_available_room(building, gender, platoon, squad, floor=None, **flags):
        """
        Tries to assign a room starting from a selected floor and moves to higher floors if no rooms are available.
        - If `fill_empty_first` is True, prioritize assigning completely empty rooms before filling partially occupied ones.
        - If a squad has extra students (e.g., 12 students in a 10-person room), try merging them with another squad.
        - If merging is not possible, create a new room.
        """

        # Step 1: Try to find rooms on the specified floor first
        available_rooms = RoomAssignmentHelper.get_rooms_by_floor(building, floor)

        # Step 2: If no rooms found, move from lowest to highest
        if not available_rooms:
            available_rooms = RoomAssignmentHelper.get_rooms_by_floor(building, floor=None)

        if not available_rooms:
            raise Exception(f"Không có phòng trống trong {building.name}")

        # Step 1: Handle squad merging if squad size exceeds room capacity
        if room := RoomAssignmentHelper.fill_partial_room_first(available_rooms, gender, platoon, squad):
            return room

        # Step 2: If no partial fill is possible, create a new room
        if room := RoomAssignmentHelper.fill_empty_room_first(available_rooms, gender, platoon, squad):
            return room

        raise Exception(f"Không có phòng phù hợp cho {platoon.name} - {squad} trong {building.name}")

    @staticmethod
    def get_rooms_by_floor(building, floor=None):
        """Fetches available rooms starting from the selected floor up to the building's total floors."""
        room_filter = {
            "building": building,
            "is_lock": False,
            "is_temporary_lock": False
        }

        if floor:
            # Ensure we start from the given floor
            floors_query = Floor.objects.filter(building=building, floor_number__gte=floor.floor_number)
        else:
            # Start from the lowest floor if no floor is specified
            floors_query = Floor.objects.filter(building=building)

        # Get available rooms (only those with space left)
        rooms_query = (
            Room.objects.filter(**room_filter, floor__in=floors_query)
            .annotate(occupancy=models.Count("student"))
            .filter(occupancy__lt=models.F("capacity"))  # Only rooms with available space
            .order_by("floor__floor_number")  # Prioritize lower floors
        )

        return list(rooms_query)  # Convert queryset to list for iteration

    @staticmethod
    def fill_empty_room_first(available_rooms, gender, platoon, squad):
        """Assigns the first completely empty room found."""
        for room in available_rooms:
            if not Student.objects.filter(room=room).exists():
                return room  # ✅ Return the first empty room found

        return None  # No empty rooms available

    @staticmethod
    def fill_partial_room_first(available_rooms, gender, platoon, squad):
        """Assigns a partially filled room with capacity left, ensuring compatibility."""
        for room in available_rooms:
            student_count = Student.objects.filter(room=room).count()
            if 0 < student_count < room.capacity:
                can_add = RoomAssignmentHelper.validate_room(room, gender=gender, platoon=platoon, squad=squad)
                if can_add:
                    return room  # ✅ Return the first suitable partially filled room

        return None  # No partially filled rooms available

    @staticmethod
    def validate_room(room, **conditions):
        """
        Generic function to validate if a student can be assigned to a given room.
        Automatically detects field types and ensures correct comparisons.

        :param room: Room instance to validate
        :param conditions: Dictionary of conditions to check (e.g., gender="nữ", squad=3, platoon="Platoon A")
        :return: True if room matches all conditions, False otherwise
        """

        first_student = Student.objects.filter(room=room).first()
        if not first_student:
            return True  #

        for field, expected_value in conditions.items():
            if hasattr(first_student, field):
                actual_value = getattr(first_student, field)

                if isinstance(actual_value, Platoon) and isinstance(expected_value, Platoon):
                    if actual_value.name.strip().lower() != expected_value.name.strip().lower():
                        return False  #

                elif isinstance(actual_value, str) or isinstance(expected_value, str):
                    if str(actual_value).strip().lower() != str(expected_value).strip().lower():
                        return False  #

                elif isinstance(actual_value, (int, float)) and isinstance(expected_value, (int, float)):
                    if actual_value != expected_value:
                        return False  #

                else:
                    return False  #

        return True  # ✅ Room matches all conditions

    @staticmethod
    def assign_room_by_building_and_floor(instance, selected_building_name, selected_floor_number, **flags):
        """
        Assign a student to an available room in the selected building and floor.
        """

        if not selected_building_name:
            raise Exception("No valid building name")

        building = Building.objects.filter(name=selected_building_name).first()
        if not building:
            raise Exception(f"Building '{selected_building_name}' does not exist.")

        if not selected_floor_number:
            raise Exception("No valid floor number")

        # Ensure `floor` is an instance of `Floor`
        floor = Floor.objects.filter(building=building, floor_number=selected_floor_number).first()
        if not floor:
            raise Exception(f"Floor {selected_floor_number} does not exist in {selected_building_name}.")

        # Pass the `floor` instance (not an integer) to `_get_available_room()`
        instance.room = RoomAssignmentHelper.get_available_room(building, instance.gender, instance.platoon,
                                                                instance.squad, floor=floor, **flags)

    @staticmethod
    def merge_students_before_saving(*args, **kwargs):
        try:
            # Fetch all buildings
            buildings = Room.objects.values_list("building", flat=True).distinct()

            students_to_update = []  # Track students needing updates

            for building in buildings:
                # Skip the building if the **first room itself is empty**
                total_students_in_building = Student.objects.filter(room__building=building).count()
                if total_students_in_building == 0:
                    continue  # Skip this building if completely empty

                # Get rooms in the building
                rooms_in_building = (
                    Room.objects.filter(building=building, is_temporary_lock=False, is_lock=False)
                    .annotate(student_count=Count("student"))
                )

                # Get rooms in the same building that are under-occupied
                under_occupied_rooms = [
                    room for room in rooms_in_building if 0 < room.student_count < room.capacity
                ]

                # Fetch students in under-occupied rooms **within the same building**
                students_to_move = list(
                    Student.objects.filter(room__in=under_occupied_rooms)
                    .exclude(
                        room__in=[
                            room for room in under_occupied_rooms
                            if Student.objects.filter(room=room)
                               .values("platoon", "gender", "squad").distinct().count() == 1  # Room is uniform
                               and room.student_count > (room.capacity / 2)  # More than half full
                        ]
                    )
                )

                # Store student count updates in memory
                room_student_counts = {room.id: room.student_count for room in under_occupied_rooms}

                for room in under_occupied_rooms:
                    available_slots = room.capacity - room_student_counts.get(room.id, 0)

                    if available_slots == room.capacity:  # Room is completely empty
                        if students_to_move:
                            student = students_to_move.pop(0)  # Take the first student
                            student.room = room  # Assign to new room
                            student.save()
                            students_to_update.append(student)
                            available_slots -= 1  # Reduce available slots
                            room_student_counts[room.id] += 1  # Manually update count

                    # Get a first student to determine the platoon and gender of the room
                    first_student = Student.objects.filter(room=room).first()
                    if not first_student:
                        continue  # Skip empty rooms

                    room_platoon = first_student.platoon
                    room_gender = first_student.gender

                    # Ensure room is **not** uniform and less than half full before moving students out
                    if (
                            Student.objects.filter(room=room)
                                    .values("platoon", "gender", "squad")
                                    .distinct()
                                    .count() == 1  # Room is already uniform
                            and room_student_counts.get(room.id, 0) > (room.capacity / 2)  # More than half full
                    ):
                        continue  # Skip this room

                    # Find students that match the room's **platoon** and **gender** within the same building
                    filtered_students = [
                        s for s in students_to_move if s.platoon == room_platoon and s.gender == room_gender
                    ]

                    # Move students into the room while respecting constraints
                    while available_slots > 0 and filtered_students:
                        student = filtered_students.pop(0)
                        if student.room == room:
                            students_to_update.append(student)
                            students_to_move.remove(student)
                            continue

                        previous_room = student.room
                        student.room = room
                        student.save(update_fields=["room"])
                        students_to_update.append(student)
                        students_to_move.remove(student)

                        available_slots -= 1
                        room_student_counts[room.id] += 1
                        room_student_counts[previous_room.id] -= 1

            return students_to_update  # Return updated students

        except Exception as e:
            logging.error(f"Error in merging students: {e}")
            return []

    @staticmethod
    def arrange_students_within_building(*args, **kwargs):
        try:
            # Fetch all buildings
            buildings = Room.objects.values_list("building", flat=True).distinct()

            for building in buildings:
                # Check if the building has any students
                total_students_in_building = Student.objects.filter(room__building=building).count()
                if total_students_in_building == 0:
                    continue  # Skip this building if completely empty

                # Get rooms in the same building
                rooms_in_building = list(
                    Room.objects.filter(building=building, is_temporary_lock=False, is_lock=False)
                    .annotate(student_count=Count("student"))
                )

                # Iterate through rooms and shift students forward
                for i in range(len(rooms_in_building)):
                    current_room = rooms_in_building[i]

                    # If current room is NOT empty, move to the next one
                    if current_room.student_count > 0:
                        continue

                    # Find the next room that actually has students
                    next_occupied_room = None
                    for j in range(i + 1, len(rooms_in_building)):  # Look ahead
                        if rooms_in_building[j].student_count > 0:
                            next_occupied_room = rooms_in_building[j]
                            break  # Stop at the first occupied room

                    # If no occupied room was found, stop processing
                    if not next_occupied_room:
                        break  # No more students to move, exit loop

                    # Move students from the next occupied room to fill the current room
                    students_to_move = Student.objects.filter(room=next_occupied_room).order_by("id")

                    for student in students_to_move:
                        student.room = current_room  # Assign student to the empty room
                        student.save()
                        current_room.student_count += 1
                        next_occupied_room.student_count -= 1

                        # Stop moving when the current room is full
                        if current_room.student_count >= current_room.capacity:
                            break

            return True  # Successfully rearranged students

        except Exception as e:
            logging.error(f"Error in arranging students: {e}")
            return False