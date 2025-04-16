from collections import defaultdict

from django.db import models
from django.db.models import Count, F

from backend.helper import RoomAssignmentHelper
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
    def assign_remaining_students_fallback():
        """
        Try to assign remaining unassigned students (in cache)
        using a fallback strategy:
        1. Same platoon + gender rooms with space
        2. Empty room closest to existing platoon rooms
        """
        remaining = RoomAssignmentCache.get_all()
        reassigned = []

        for entry in remaining:
            student = entry["instance"]

            # STEP 1: Try to find a room with same platoon + gender
            room = StudentUtils._find_room_same_platoon(student)

            # STEP 2: Fallback to empty room near platoon's rooms
            if not room:
                room = StudentUtils._find_empty_room_near_platoon(student.platoon)

            if room:
                student.room = room
                student.save()

                if Student.objects.filter(room=room).count() >= room.capacity:
                    room.is_lock_to_move = True
                    room.save()

                reassigned.append(student)

        # Cleanup cache: remove reassigned
        RoomAssignmentCache._unassigned_instances = [
            entry for entry in RoomAssignmentCache.get_all()
            if entry["instance"] not in reassigned
        ]

    @staticmethod
    def _find_room_same_platoon(student):
        return (
            Room.objects.filter(
                is_lock=False,
                is_temporary_lock=False,
                is_lock_to_move=False,
                student__platoon=student.platoon,
                student__gender=student.gender
            )
            .annotate(occupancy=Count("student"))
            .filter(occupancy__lt=F("capacity"))
            .order_by("floor__floor_number", "room_code")
            .distinct()
            .first()
        )

    @staticmethod
    def _find_empty_room_near_platoon(platoon):
        """
        Get empty rooms, prioritized by being close to where this platoon already lives.
        """
        # Get room_ids where the platoon already exists
        existing_room_ids = (
            Student.objects.filter(platoon=platoon)
            .values_list("room_id", flat=True)
        )

        existing_rooms = Room.objects.filter(id__in=existing_room_ids).select_related("floor")

        # Find floor numbers used by this platoon
        platoon_floors = set(room.floor.floor_number for room in existing_rooms if room.floor)

        # Find all empty rooms
        empty_rooms = (
            Room.objects.filter(
                is_lock=False,
                is_temporary_lock=False,
                is_lock_to_move=False
            )
            .annotate(occupancy=Count("student"))
            .filter(occupancy=0)
            .select_related("floor")
            .order_by("floor__floor_number", "room_code")
        )

        # Prioritize empty rooms on the same floor as platoon
        for room in empty_rooms:
            if room.floor and room.floor.floor_number in platoon_floors:
                return room

        # If no floor-match found, fallback to first empty room
        return empty_rooms.first()


