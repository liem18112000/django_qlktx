from collections import defaultdict

from django.db import transaction
from django.db.models import Count

from backend.models import Room, Student, Building
from backend.room_cache import RoomAssignmentCache


class StudentUtils:
    @staticmethod
    def get_unassigned_grouped_by_platoon_squad():
        """
        Return a nested dict of unassigned student instances grouped by:
        - Platoon (as a top-level key)
        - Squad number (sorted ascending within each platoon)
        """
        raw_entries = RoomAssignmentCache.get_all()
        grouped = defaultdict(lambda: defaultdict(list))

        for entry in raw_entries:
            student = entry["instance"]
            platoon = getattr(student, "platoon", "Unknown")
            squad = getattr(student, "squad", 0)
            grouped[platoon][squad].append(student)

        # Sort squads within each platoon
        sorted_result = {}
        for platoon, squads in grouped.items():
            sorted_result[platoon] = {
                squad: squads[squad]
                for squad in sorted(squads.keys())
            }

        return sorted_result

    @staticmethod
    def handle_mixed_squad_with_same_platoon(selected_building_name=None):
        source_buildings = (Building.objects
                            .annotate(student_counts=Count("room__student"))
                            .filter(under_occupied=False)
                            .order_by("-male_priority", "-female_priority")
                            )
        dest_buildings = []

        # 1. If there's a selected building, add it first
        if selected_building_name:
            selected_building = Building.objects.get(name=selected_building_name)
            source_buildings.append(selected_building)

            # 2. Get the rest, excluding selected one
            other_buildings = (Building.objects
                               .annotate(student_counts=Count("room__student"))
                               .filter(under_occupied=True, student_counts__gt=0)
                               .order_by("-male_priority", "-female_priority")
                               )
        else:
            # No selected, just get all source buildings in priority order
            other_buildings = (Building.objects
                               .annotate(student_counts=Count("room__student"))
                               .filter(under_occupied=True, student_counts__gt=0)
                               .order_by("-male_priority", "-female_priority")
                               )

        # 3. Combine into final ordered list
        dest_buildings += list(other_buildings)

        # 💡 room status tracking
        room_status = {}
        platoon_room_map = defaultdict(list)

        for building in dest_buildings:
            rooms = (
                Room.objects
                .filter(building=building)
                .annotate(student_counts=Count("student"))
                .filter(student_counts__gt=0)
            )

            for room in rooms:
                students = list(room.student_set.all())
                if not students:
                    continue

                # Lấy majority platoon
                majority_platoon = StudentUtils.get_majority_platoon(students)
                gender = students[0].gender
                key = (majority_platoon, gender)

                # Store room in map
                platoon_room_map[key].append(room)

                # Track room status in-memory
                room_status[room.id] = {
                    "count": len(students),
                    "gender": gender,
                    "platoon": majority_platoon
                }

        # Di chuyển học sinh từ building under_occupied=False
        for building in source_buildings:
            source_rooms = (
                Room.objects
                .filter(building=building, is_lock_to_move=False)
                .annotate(
                    student_counts=Count("student"),
                    platoon_distinct=Count("student__platoon", distinct=True),
                    squad_distinct=Count("student__squad", distinct=True)
                )
                .filter(student_counts__gt=0)
            )

            for room in source_rooms:

                allow_to_move = (room.platoon_distinct + room.squad_distinct == 2) and room.student_counts < 5
                if allow_to_move is False:
                    continue

                for student in room.student_set.all():
                    key = (student.platoon, student.gender)

                    for dest_room in platoon_room_map.get(key, []):
                        status = room_status[dest_room.id]

                        if status["count"] < dest_room.capacity:
                            # Gán học sinh
                            student.room = dest_room
                            student.save()

                            # Cập nhật in-memory
                            room_status[dest_room.id]["count"] += 1

                            break  # next student

    @staticmethod
    def get_majority_platoon(students):
        from collections import Counter
        platoons = [s.platoon for s in students]
        if not platoons:
            return None
        return Counter(platoons).most_common(1)[0][0]

    @staticmethod
    def handle_filling_student_across_building(selected_building_name=None):
        source_buildings = (Building.objects
                            .annotate(student_counts=Count("room__student"))
                            .filter(under_occupied=False)
                            .order_by("-male_priority", "-female_priority")
                            )
        dest_buildings = []

        # 1. If there's a selected building, add it first
        if selected_building_name:
            selected_building = Building.objects.get(name=selected_building_name)
            source_buildings.append(selected_building)

            # 2. Get the rest, excluding selected one
            other_buildings = (Building.objects
                               .annotate(student_counts=Count("room__student"))
                               .filter(under_occupied=True, student_counts__gt=0)
                               .order_by("-male_priority", "-female_priority")
                               )
        else:
            # No selected, just get all source buildings in priority order
            other_buildings = (Building.objects
                               .annotate(student_counts=Count("room__student"))
                               .filter(under_occupied=True, student_counts__gt=0)
                               .order_by("-male_priority", "-female_priority")
                               )

        # 3. Combine into final ordered list
        dest_buildings += list(other_buildings)

        source_students = StudentUtils.collect_source_students(source_buildings)
        room_status, gender_room_map, empty_room_map = StudentUtils.prepare_destination_rooms(dest_buildings)
        StudentUtils.move_students_by_floor_priority(source_students, room_status, gender_room_map,
                                                     empty_room_map)

    @staticmethod
    def collect_source_students(source_buildings):
        def should_skip_room(room):
            if room.student_set.count() == room.capacity:
                return True
            platoons = list(room.student_set.values_list("platoon", flat=True))
            squads = list(room.student_set.values_list("squad", flat=True))
            platoon_count = len(set(platoons))
            squad_count = len(set(squads))
            if platoon_count + squad_count == 1 and len(platoons) > 5:
                return True
            return False

        source_students = []

        for building in source_buildings:
            rooms = (
                Room.objects
                .annotate(student_counts=Count("student"))
                .filter(building=building, student_counts__gt=0, is_lock_to_move=False)
                .select_related("floor")
                .prefetch_related("student_set")
                .order_by("floor__floor_number")
            )

            for room in rooms:
                if should_skip_room(room):
                    continue
                floor = room.floor.floor_number if room.floor else 0
                for student in room.student_set.all():
                    source_students.append({
                        "student": student,
                        "floor": floor
                    })

        # Sort tầng thấp lên
        return sorted(source_students, key=lambda s: s["floor"])

    @staticmethod
    def prepare_destination_rooms(dest_buildings):

        room_status = {}
        gender_room_map = defaultdict(list)
        empty_room_map = defaultdict(list)

        for building in dest_buildings:
            rooms = (
                Room.objects
                .filter(building=building)
                .select_related("floor")
                .prefetch_related("student_set")
                .order_by("floor__floor_number")
            )

            for room in rooms:
                students = list(room.student_set.all())
                gender = students[0].gender if students else None

                room_status[room.id] = {
                    "count": len(students),
                    "gender": gender,
                    "capacity": room.capacity,
                }

                if students:
                    gender_room_map[gender].append(room)
                else:
                    empty_room_map[building].append(room)

        return room_status, gender_room_map, empty_room_map

    @staticmethod
    def move_students_by_floor_priority(source_students, room_status, gender_room_map, empty_room_map):
        for entry in source_students:
            student = entry["student"]
            assigned = False

            # Ưu tiên phòng cùng giới đã có người
            for room in gender_room_map.get(student.gender, []):
                status = room_status[room.id]
                if status["count"] < status["capacity"]:
                    student.room = room
                    student.save()
                    status["count"] += 1
                    assigned = True
                    break

            # Fallback: phòng trống
            if not assigned:
                for building, room_list in empty_room_map.items():
                    for empty_room in room_list:
                        status = room_status[empty_room.id]
                        if status["count"] < status["capacity"]:
                            student.room = empty_room
                            student.save()
                            status["count"] += 1
                            status["gender"] = student.gender
                            gender_room_map[student.gender].append(empty_room)
                            assigned = True
                            break
                    if assigned:
                        break

            if not assigned:
                print(f"student could not be assigned.")

    @staticmethod
    @transaction.atomic
    def fill_empty_rooms_in_dest_from_source(selected_building_name=None):
        dest_buildings = []

        # 1. If there's a selected building, add it first
        if selected_building_name:
            selected_building = Building.objects.get(name=selected_building_name)
            dest_buildings.append(selected_building)

            # 2. Get the rest, excluding selected one
            other_buildings = Building.objects.filter(
                under_occupied=True
            ).exclude(id=selected_building.id).order_by(
                '-male_priority', '-female_priority'
            )
        else:
            # No selected, just get all source buildings in priority order
            other_buildings = Building.objects.annotate(
                student_count=Count('room__student')
            ).filter(
                under_occupied=True,
                student_count__gt=0
            ).order_by('-male_priority', '-female_priority')

        dest_buildings += list(other_buildings)

        # Get all empty rooms in these buildings
        empty_rooms = Room.objects.filter(
            building__in=dest_buildings
        ).annotate(
            current_count=Count('student')
        ).filter(current_count=0).order_by(
            '-building__male_priority',
            '-building__female_priority',
            'floor__floor_number',
        )

        if not empty_rooms:
            return  # không có phòng trống

        source_buildings = Building.objects.filter(
            under_occupied=False
        ).order_by('-male_priority', '-female_priority')

        # Get all eligible students from non-under_occupied buildings
        students = Student.objects.filter(
            room__building__in=source_buildings,
            room__is_lock_to_move=False
        ).select_related('room', 'room__building').order_by(
            '-room__building__male_priority',
            '-room__building__female_priority',
            'room__floor__floor_number',
        )

        # Gán từng học sinh vào phòng trống
        room_iter = iter(empty_rooms)
        current_room = next(room_iter, None)
        if not current_room:
            return

        filled = 0
        cap = current_room.capacity

        for student in students:
            # assign và lưu
            student.room = current_room
            student.save(update_fields=['room'])

            filled += 1
            # nếu phòng đã đầy, chuyển sang phòng kế tiếp
            if filled >= cap:
                current_room = next(room_iter, None)
                if current_room is None:
                    break
                filled = 0
                cap = current_room.capacity
