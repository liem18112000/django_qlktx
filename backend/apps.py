from django.apps import AppConfig


class BackendConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend"
    verbose_name = "Quản lý Ký túc xá"

    def ready(self):
        import backend.signals
