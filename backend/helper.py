import logging

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
                print(f"Skipping building {building.name}: {e}")
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

        # Step 3: Prioritize filling partially filled rooms if the flag is set
        if flags.get("fill_partial_first"):
            if room := RoomAssignmentHelper.fill_partial_room_first(available_rooms, gender, platoon, squad):
                return room

        # Step 4: Prioritize filling empty rooms if the flag is set
        if flags.get("fill_empty_first"):
            if room := RoomAssignmentHelper.fill_empty_room_first(available_rooms, gender, platoon, squad):
                return room

        # Step 5: Handle squad merging if squad size exceeds room capacity
        if room := RoomAssignmentHelper.fill_partial_room_first(available_rooms, gender, platoon, squad):
            return room

        # Step 8: If no partial fill is possible, create a new room
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
            .order_by("floor__floor_number", "room_code")  # Prioritize lower floors
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
    def assign_students_to_room(platoon, squad, room, num_students=None):
        """
        Assigns students from a squad into a given room.

        - If `num_students` is None, it assigns all students from the squad.
        - Otherwise, it assigns only `num_students` from the squad.
        - Ensures students are placed in the same room if possible.
        """

        # Fetch students who need to be assigned
        student_query = Student.objects.filter(platoon=platoon, squad=squad, room__isnull=True)

        # If num_students is set, limit the number of students to be assigned
        if num_students:
            student_query = student_query[:num_students]

        students_to_assign = list(student_query)

        if not students_to_assign:
            return None  # No students available to assign

        # Assign students to the room
        for student in students_to_assign:
            student.room = room
            student.save()  # ✅ Update database

        return room  # ✅ Return the assigned room

    @staticmethod
    def merge_students_before_saving(*args, **kwargs):
        try:
            # ✅ Find rooms that are under-occupied (not full but have students)
            under_occupied_rooms = (
                Room.objects.annotate(student_count=Count("student"))  # Count related students
                .filter(student_count__gt=0, student_count__lt=F("capacity"))  # Not empty, not full
                .order_by("room_code")  # Order by room_code
            )

            # ✅ Convert rooms to list for processing
            target_rooms = list(under_occupied_rooms)

            # ✅ Get students from under-occupied rooms
            students_to_move = list(Student.objects.filter(room__in=under_occupied_rooms).order_by("id"))

            # ✅ Track students that need updating
            students_to_update = []

            # ✅ Start merging students while respecting platoon alignment
            for room in target_rooms:
                available_slots = room.capacity - room.student_count  # How many students can fit?

                # ✅ Get the first student in the room
                first_student = Student.objects.filter(room=room).first()
                if not first_student:
                    continue  # Skip if no students in the room

                room_platoon = first_student.platoon
                room_gender = first_student.gender

                # ✅ Move students from under-occupied rooms, but only if they match the platoon and gender
                filtered_students = [s for s in students_to_move if
                                     s.platoon == room_platoon and s.gender == room_gender]

                while available_slots > 0 and filtered_students:
                    student = filtered_students.pop(0)  # Take the first matching student
                    student.room = room  # Move student to the new room
                    students_to_update.append(student)  # Add student to update list
                    students_to_move.remove(student)  # Remove from global list
                    available_slots -= 1  # Reduce available slots

            # ✅ Bulk update all moved students at once for efficiency
            if students_to_update:
                Student.objects.bulk_update(students_to_update, ["room"])

        except Exception as e:
            logging.error(f"error in merging: {e}")
            return
