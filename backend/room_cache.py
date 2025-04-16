import threading


class RoomAssignmentCache:
    _lock = threading.Lock()
    _unassigned_instances = []

    @classmethod
    def add_unassigned(cls, instance, reason=None):
        with cls._lock:
            for entry in cls._unassigned_instances:
                existing = entry["instance"]

                # 1. Compare by primary key
                if instance.pk is not None and existing.pk == instance.pk:
                    return  # Duplicate based on PK

                # 2. Fallback: Compare by field values if both are unsaved
                if instance.pk is None and existing.pk is None:
                    if cls._instances_equal(instance, existing):
                        return  # Duplicate found

            # Add instance if no duplicate found
            cls._unassigned_instances.append({
                "instance": instance,
                "reason": reason or "No available room"
            })

    @staticmethod
    def _instances_equal(a, b):
        """
        Compare two model instances based on their field values (not memory address).
        Skips auto fields and relations.
        """
        if a.__class__ != b.__class__:
            return False

        # You can refine this logic to exclude volatile or non-identifying fields
        fields_to_check = [
            field.name for field in a._meta.fields
            if not field.auto_created and not field.primary_key
        ]

        for field_name in fields_to_check:
            if getattr(a, field_name) != getattr(b, field_name):
                return False
        return True

    @classmethod
    def get_all(cls):
        with cls._lock:
            return list(cls._unassigned_instances)  # return a copy

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._unassigned_instances.clear()

    @classmethod
    def clean_assigned_instances(cls):
        """
        Remove any instances that now have a room assigned.
        """
        with cls._lock:
            cls._unassigned_instances = [
                entry for entry in cls._unassigned_instances
                if not getattr(entry["instance"], "room_id", None)
            ]