
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_qlktx.settings")
try:
    print("Before setup...")
    django.setup()
    print("After setup...")
except Exception as e:
    print(f"Error during django.setup(): {e}")