
from django.db.models import Count

from backend.models import Building


class BuildingUtils:
    @staticmethod
    def get_buildings_with_rooms():
        """
        Return a nested mapping of Buildings to their Rooms to list of Students,
        with room-level annotations for student count, distinct platoon and squad counts.
        Structure: { Building: { Room: [Student, ...], ... }, ... }
        """
        buildings = Building.objects.prefetch_related('room_set')
        building_rooms = {}
        for b in buildings:
            # Annotate room stats
            rooms_qs = b.room_set.annotate(
                student_count=Count('student'),
                distinct_platoon_count=Count('student__platoon', distinct=True),
                distinct_squad_count=Count('student__squad', distinct=True)
            )
            room_map = {}
            for room in rooms_qs:
                # Fetch all students in this room
                students = list(room.student_set.select_related('platoon').all())
                room_map[room] = students
            building_rooms[b] = room_map
        return building_rooms

    @staticmethod
    def update_building_under_occupied():

        buildings = Building.objects.prefetch_related('room_set')  # use related_name if defined

        for building in buildings:
            rooms = building.room_set.all()  # use .room_set.all() if no related_name

            # Skip building with no rooms
            if not rooms.exists():
                building.under_occupied = False
                building.save()
                continue

            # Check if all rooms have at least 1 student
            all_rooms_have_students = all(room.student_set.exists() for room in rooms)

            building.under_occupied = all_rooms_have_students
            building.save()

    @staticmethod
    def unlock_building_with_empty_room():
        buildings = Building.objects.prefetch_related('room_set')

        for building in buildings:
            rooms = building.room_set.all()  # or room_set if no related_name

            # If ANY room is empty, unlock it
            has_empty_room = any(not room.student_set.exists() for room in rooms)

            if has_empty_room and building.under_occupied:
                building.under_occupied = False
                building.save()
                print(f" Building {building.name} unlocked (found empty room)")