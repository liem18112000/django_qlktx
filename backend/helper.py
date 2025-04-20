import logging
from collections import defaultdict

from django.db import models
from django.db.models import Count

from .models import Room, Student, Building, Floor, Platoon


class RoomAssignmentHelper:
    """
    Helper class to manage room assignments for students.
    """
    has_oversized_student = True
    processed_squads_by_platoon = set()  # chứa tuple (platoon, squad)
    has_unassigned_student = False

    @staticmethod
    def assign_room_directly(instance, building, room_code):
        """Assign the student directly to a specific room in a building."""
        try:
            room = Room.objects.get(
                building=building,
                room_code=room_code,
                is_lock=False,
                is_temporary_lock=False,
            )
            instance.room = room

        except Room.DoesNotExist:
            raise Exception("No Room in building")

    @staticmethod
    def assign_room_in_building(instance, building, **flags):
        """Find an available room inside the specified building."""
        instance.room = RoomAssignmentHelper.get_available_room(building, instance.gender, instance.platoon,
                                                                instance.squad, **flags)

    @staticmethod
    def assign_room_by_priority(instance, **flags):
        """Assign a building based on gender priority."""
        gender = instance.gender
        buildings = RoomAssignmentHelper.get_first_building_with_available_room(gender)

        for building in buildings:
            instance.room = RoomAssignmentHelper.get_available_room(building, gender, instance.platoon,
                                                                    instance.squad, None, instance, **flags)
            room = getattr(instance, "room", None)
            if room is not None:
                return

    @staticmethod
    def get_first_building_with_available_room(gender):
        result = []
        # Lấy danh sách building theo thứ tự ưu tiên
        buildings = Building.objects.all().order_by(
            '-female_priority' if gender == "Nữ" else '-male_priority'
        )

        for building in buildings:
            rooms = Room.objects.filter(building=building)

            for room in rooms:
                # Đếm số student đã gán vào room này (optional: lọc theo gender)
                current_count = Student.objects.filter(room=room).count()

                if current_count < room.capacity:
                    result.append(building)
                    break  # Chỉ cần 1 room trống là ok rồi
        return result

    @staticmethod
    def assign_room_by_selected_building(instance, selected_building_name=None, **flags):
        """Assign student to an available room in the selected building."""
        if not selected_building_name:
            raise Exception("Tên tòa nhà không hợp lệ.")

        building = Building.objects.filter(name=selected_building_name).first()

        if not building:
            raise Exception(f"Tòa nhà '{selected_building_name}' không tồn tại.")

        instance.room = RoomAssignmentHelper.get_available_room(building, instance.gender, instance.platoon,
                                                                instance.squad, None, instance, **flags)
        room = getattr(instance, "room", None)
        if room is None:
            RoomAssignmentHelper.assign_room_by_priority(instance)

    @staticmethod
    def get_building_with_gender(instance):
        """Assign a building based on gender priority."""
        gender = instance.gender
        buildings = Building.objects.all().order_by(
            '-female_priority' if gender == "Nữ" else '-male_priority'
        )
        return buildings

    @staticmethod
    def get_available_room(building, gender, platoon, squad, floor=None, *args, **flags):
        """
        Tries to assign a room starting from a selected floor and moves to higher floors if no rooms are available.
        - If `fill_empty_first` is True, prioritize assigning completely empty rooms before filling partially occupied ones.
        - If a squad has extra students (e.g., 12 students in a 10-person room), try merging them with another squad.
        - If merging is not possible, create a new room.
        """
        student_qs = args[0]
        # Step 1: Try to find rooms on the specified floor first
        available_rooms = RoomAssignmentHelper.get_rooms_by_floor(building, floor)

        # Step 2: If no rooms found, move from lowest to highest
        if not available_rooms:
            available_rooms = RoomAssignmentHelper.get_rooms_by_floor(building, floor=None)

        if not available_rooms:
            return None

        # Step 1: Handle squad merging if squad size exceeds room capacity
        if room := RoomAssignmentHelper.fill_partial_room_first(available_rooms, gender, platoon, squad):
            RoomAssignmentHelper.processed_squads_by_platoon.add((student_qs.platoon, student_qs.squad))
            return room

        # Step 2: If no partial fill is possible, create a new room

        if room := RoomAssignmentHelper.fill_empty_room_first(available_rooms, gender, platoon, squad):
            return room

        return None

    @staticmethod
    def _extract_instance_details(instance):
        """Extract and preprocess instance attributes."""
        room_code = getattr(instance, "room_code", None)
        if isinstance(room_code, int):
            room_code = str(room_code)

        gender = getattr(instance, "gender", None)
        platoon_name = getattr(instance, "platoon", None)
        squad = getattr(instance, "squad", None)
        building = getattr(instance, "building", None)
        if isinstance(building, str):
            building = Building.objects.get(name=building)

        # Get Platoon object safely
        platoon = Platoon.objects.get(name=platoon_name) if platoon_name else None

        return room_code, gender, platoon, squad, building

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
                return room  # Return the first empty room found

        return None  # No empty rooms available

    @staticmethod
    def fill_partial_room_first(available_rooms, gender, platoon, squad):
        """Assigns a partially filled room with capacity left, ensuring compatibility."""
        for room in available_rooms:
            student_count = Student.objects.filter(room=room).count()
            if 0 < student_count < room.capacity:
                can_add = RoomAssignmentHelper.validate_room(room, gender=gender, platoon=platoon, squad=squad)
                if can_add:
                    return room  # Return the first suitable partially filled room

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

        return True  # Room matches all conditions

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
        instance.room = RoomAssignmentHelper.get_available_room(building, instance, floor=floor, **flags)

    @staticmethod
    def merge_students_before_saving():
        try:
            from_buildings = Room.objects.values_list("building", flat=True).distinct()
            students_to_update = []

            for building in from_buildings:
                total_students_in_building = Student.objects.filter(room__building=building).count()
                if total_students_in_building == 0:
                    continue

                rooms_in_building = (
                    Room.objects.filter(building=building, is_temporary_lock=False, is_lock=False)
                    .annotate(
                        student_count=Count("student"),
                        distinct_platoon=Count("student__platoon", distinct=True),
                        distinct_squad=Count("student__squad", distinct=True),
                        distinct_gender=Count("student__gender", distinct=True),
                    )
                )

                under_occupied_rooms = [
                    room for room in rooms_in_building
                    if 0 < room.student_count < room.capacity and room.distinct_platoon + room.distinct_gender == 2
                ]

                # Create a lookup for faster access
                room_lookup = {room.id: room for room in under_occupied_rooms}

                students_to_move = list(
                    Student.objects.filter(room__in=under_occupied_rooms)
                    .exclude(
                        room__in=[
                            room for room in under_occupied_rooms
                            if (
                                       room.distinct_platoon + room.distinct_squad + room.distinct_gender == 3
                                       and room.student_count > (room.capacity / 2)
                               ) or room.distinct_platoon + room.distinct_squad + room.distinct_gender != 3
                        ]
                    )
                )

                room_student_counts = {room.id: room.student_count for room in under_occupied_rooms}

                for room in under_occupied_rooms[:]:  # Copy list to safely modify it inside loop
                    available_slots = room.capacity - room_student_counts.get(room.id, 0)

                    if available_slots <= 0:
                        continue  # Skip if already full

                    if room_student_counts[room.id] == 0:
                        if students_to_move:
                            student = students_to_move.pop(0)
                            previous_room = student.room
                            student.room = room
                            student.save(update_fields=["room"])
                            students_to_update.append(student)
                            room_student_counts[room.id] += 1
                            room_student_counts[previous_room.id] -= 1
                            available_slots -= 1
                        else:
                            continue

                    first_student = Student.objects.filter(room=room).first()
                    if not first_student:
                        continue

                    room_platoon = first_student.platoon
                    room_gender = first_student.gender

                    filtered_students = [
                        s for s in students_to_move if s.platoon == room_platoon and s.gender == room_gender
                    ]

                    while available_slots > 0 and filtered_students:
                        student = filtered_students.pop(0)
                        if student.room.id == room.id:
                            students_to_update.append(student)
                            students_to_move.remove(student)
                            continue

                        previous_room = student.room
                        student.room = room
                        student.save(update_fields=["room"])
                        students_to_update.append(student)
                        students_to_move.remove(student)

                        room_student_counts[room.id] += 1
                        room_student_counts[previous_room.id] -= 1
                        available_slots -= 1

                    # Remove from a target list if full
                    if room_student_counts[room.id] >= room.capacity:
                        under_occupied_rooms = [
                            r for r in under_occupied_rooms if r.id != room.id
                        ]

            RoomAssignmentHelper.arrange_students_within_building()
            return students_to_update

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

                # Get rooms in the same building, excluding locked ones
                rooms_in_building = list(
                    Room.objects.filter(building=building, is_temporary_lock=False, is_lock=False)
                    .annotate(student_count=Count("student"))
                )

                # Iterate through rooms and shift students forward while preserving order
                for i in range(len(rooms_in_building)):
                    current_room = rooms_in_building[i]

                    # If the current room is NOT empty, move to the next one
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
                        break  # No more students to move, continue to seach another building

                    # Move students from the next occupied room to fill the current room, keeping order
                    students_to_move = Student.objects.filter(room=next_occupied_room).order_by("id")

                    for student in students_to_move:
                        student.room = current_room  # Assign student to the empty room
                        student.save()
                        current_room.student_count += 1
                        next_occupied_room.student_count -= 1

                        # Stop moving when the current room is full
                        if current_room.student_count >= current_room.capacity:
                            break

            return True

        except Exception as e:
            logging.error(f"Error in arranging students: {e}")
            return False

    @staticmethod
    def get_buildings_with_priority(selected_building_name=None):
        """
        Fetch buildings, prioritizing those suited for the given gender (default: male).
        If selected_building_name is provided, it will be placed first.
        Otherwise, the building with the highest total capacity for the priority gender is placed first.
        """
        buildings = []
        selected_building = None

        if selected_building_name:
            try:
                selected_building = Building.objects.get(name=selected_building_name)
            except Building.DoesNotExist:
                raise Exception(f"Building with name '{selected_building_name}' does not exist.")

        if selected_building:
            buildings.append(selected_building)

        # Fetch all building IDs used in rooms, excluding the selected one
        used_building_ids = Room.objects.values_list("building", flat=True).distinct()
        if selected_building:
            used_building_ids = used_building_ids.exclude(pk=selected_building.pk)

        # Get the remaining buildings
        remaining_buildings = Building.objects.filter(id__in=used_building_ids).order_by("male_priority")
        buildings += list(remaining_buildings)

        if not buildings:
            raise Exception("No building to fill.")

        return buildings

    @staticmethod
    def fill_student_to_room_after_merge(last_room_dict=None, selected_building_name=None):
        try:
            students_to_update = []

            buildings = Room.objects.values_list("building", flat=True).distinct()

            for building in buildings:
                total_students = Student.objects.filter(room__building=building).count()
                if total_students == 0:
                    continue

                # Nếu có last_room_dict và có phòng cuối cùng cho toà này, chỉ xét các phòng có ID lớn hơn
                room_queryset = Room.objects.filter(
                    building=building,
                    is_temporary_lock=False,
                    is_lock=False
                )

                if last_room_dict and building in last_room_dict:
                    last_room = last_room_dict[building]
                    room_queryset = room_queryset.filter(id__gt=last_room.id)

                rooms = room_queryset.annotate(
                    student_count=Count("student")
                ).order_by("id")

                under_occupied_rooms = [
                    room for room in rooms if 0 < room.student_count < room.capacity
                ]

                # Chỉ chọn những phòng có nhiều hơn 1 nhóm
                eligible_rooms = []
                for room in under_occupied_rooms:
                    unique_group_count = Student.objects.filter(room=room).values(
                        "platoon", "gender", "squad"
                    ).distinct().count()
                    if unique_group_count > 1:
                        eligible_rooms.append(room)

                if not eligible_rooms:
                    continue

                room_student_counts = {room.id: room.student_count for room in under_occupied_rooms}
                full_rooms = set()

                eligible_rooms.sort(key=lambda r: r.id)

                for target_room in under_occupied_rooms:
                    if target_room.id in full_rooms:
                        continue

                    if room_student_counts[target_room.id] >= target_room.capacity:
                        full_rooms.add(target_room.id)
                        continue

                    source_students = list(
                        Student.objects.filter(
                            room__in=[r for r in eligible_rooms if r.id > target_room.id and r.is_lock_to_move is False]
                        )
                        .exclude(room=target_room)
                        .select_related("room")
                        .order_by('room__id', 'squad')  # rooms with most students first
                    )

                    for student in source_students:
                        if student.room == target_room:
                            continue

                        genders = Student.objects.filter(room=target_room).values_list("gender", flat=True).distinct()
                        if genders and student.gender not in genders:
                            continue

                        current_room_id = student.room.id
                        student.room = target_room
                        students_to_update.append(student)

                        room_student_counts[target_room.id] += 1
                        room_student_counts[current_room_id] -= 1

                        if room_student_counts[target_room.id] >= target_room.capacity:
                            full_rooms.add(target_room.id)
                            break

            if students_to_update:
                Student.objects.bulk_update(students_to_update, ["room"])
                RoomAssignmentHelper.arrange_students_within_building()

            return students_to_update

        except Exception as e:
            logging.error(f"Error in fill_partial_room_after_merge: {e}")
            raise Exception(f"Error after merge: {e}")

    @staticmethod
    def move_oversize_squad_to_last():
        """
        Move fragmented squad members (within same platoon) into new rooms,
        making sure they end up in rooms beyond the last room used by their platoon.
        """
        try:
            moved_students = []
            buildings = Room.objects.values_list("building", flat=True).distinct()

            for building in buildings:
                # Get all students in the building
                students_in_building = Student.objects.filter(room__building=building)
                if not students_in_building.exists():
                    continue

                valid_room_ids = [
                    room["room"]
                    for room in Student.objects
                    .values("room")
                    .annotate(
                        distinct_platoon=Count("platoon", distinct=True),
                        distinct_squad=Count("squad", distinct=True)
                    )
                    .filter(
                        distinct_platoon=1,
                        distinct_squad=1
                    )
                ]

                students_in_building = Student.objects.filter(
                    room__building=building,
                    room__id__in=valid_room_ids
                )

                # Group students by (platoon_id, squad_id, gender)
                grouped = defaultdict(list)
                for student in students_in_building.select_related("room"):
                    key = (student.platoon, student.squad, student.gender)
                    grouped[key].append(student)

                # Process each group
                for (platoon_id, squad_id, gender), group_students in grouped.items():
                    # Group by room
                    room_to_students = defaultdict(list)
                    for student in group_students:
                        room_to_students[student.room.id].append(student)

                    # If all in one room, skip
                    if len(room_to_students) <= 1:
                        continue

                    # Identify the main room (the largest group)
                    sorted_rooms = sorted(room_to_students.items(), key=lambda x: -len(x[1]))
                    main_room_id, main_room_students = sorted_rooms[0]

                    # Find the last room used by this platoon
                    last_platoon_room = (
                        Room.objects.filter(
                            building=building,
                            student__platoon_id=platoon_id
                        )
                        .order_by("-id")
                        .first()
                    )

                    last_platoon_room_id = last_platoon_room.id if last_platoon_room else None
                    if last_platoon_room and last_platoon_room.id in room_to_students:
                        continue

                    if not last_platoon_room_id:
                        continue

                    # Find new empty room strictly after last platoon room
                    new_room = (
                        Room.objects.filter(
                            building=building,
                            is_lock=False,
                            is_temporary_lock=False,
                            student__isnull=True,
                            id__gt=last_platoon_room_id
                        )
                        .order_by("id")
                        .first()
                    )

                    if not new_room:
                        continue  # No room available

                    # Move all non-main-room students to new room
                    for room_id, students_to_move in sorted_rooms[1:]:
                        for student in students_to_move:
                            student.room = new_room
                            student.save(update_fields=["room"])
                            moved_students.append(student)

            # Re-arrange
            RoomAssignmentHelper.arrange_students_within_building()
            return moved_students

        except Exception as e:
            logging.error(f"Error in move_oversize_squad_to_last: {e}")
            return []

    @staticmethod
    def get_last_roon_have_students():
        building_with_last_room = defaultdict()
        for building in Room.objects.values_list("building", flat=True).distinct():
            total_students_in_building = Student.objects.filter(room__building=building).count()
            if total_students_in_building == 0:
                continue
            room = (
                Room.objects.annotate(student_counts=Count("student"))
                .filter(
                    building=building,
                    is_temporary_lock=False,
                    is_lock=False,
                    student_counts__gt=0,
                )
                .last()
            )
            building_with_last_room[building] = room

        return building_with_last_room

    @staticmethod
    def lock_under_occupied_rooms():
        buildings = Room.objects.values_list("building", flat=True).distinct()

        for building in buildings:
            # Get all students in the building
            students_in_building = Student.objects.filter(room__building=building)
            if not students_in_building.exists():
                continue

            under_occupied_rooms = (
                Room.objects
                .annotate(student_counts=Count("student"))
                .filter(building=building, student_counts__gt=0)
            )

            under_occupied_rooms.update(is_lock_to_move=True)

    @staticmethod
    def unlock_empty_rooms():
        buildings = Room.objects.values_list("building", flat=True).distinct()

        for building in buildings:
            # Get all students in the building

            empty_rooms_with_lock = (
                Room.objects
                .annotate(student_counts=Count("student"))
                .filter(building=building, student_counts=0, is_lock_to_move=True)

            )

            empty_rooms_with_lock.update(is_lock_to_move=False)