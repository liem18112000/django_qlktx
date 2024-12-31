import os
import PyInstaller.__main__
import django

#
APP_PATH = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(APP_PATH, "django_qlktx")
venv_path = os.path.join(APP_PATH, "venv/Lib/site-packages")

print("Django initialized successfully!")

# Include files and directories
include_files = [
    "manage.py",
    "templates/",
    "static/",
    "media/",
    "core/",
    "django_qlktx/",
    "backend/",
    "locale/"
]

# Construct additional data arguments
add_data_args = []
for file in include_files:
    file_path = os.path.abspath(file)
    add_data_args.append(f"--add-data={file_path};{file.replace(os.sep, '/')}")

hidden_imports = []

hidden_imports.extend([

])

# requirements_file = "requirements.txt"
# if os.path.exists(requirements_file):
#     with open(requirements_file, "r") as f:
#         for line in f:
#             package = line.split("==")[0].strip()
#             if package and not package.startswith("#"):
#                 hidden_imports.append(package)

# Extract libraries from requirements.txt
requirements_file = "requirements.txt"
collect_all_args =[]
# Read the packages from requirements.txt
if os.path.exists(requirements_file):
    with open(requirements_file, "r") as f:
        for line in f:
            package = line.split("==")[0].strip()
            if package and not package.startswith("#"):
                collect_all_args.append(package)

# Manually add specific packages to ensure they are included
collect_all_args.extend([
    "Django",
    "jazzmin",
    "rest_framework",
    "rest_framework_swagger",
    "corsheaders",
    "mx.DateTime",
    "django.utils",
    "drf_spectacular",
    "log_viewer",
    "django_structlog",
    "django",
    "django-filter",
    "health_check",
    "import_export",
    "rest_framework_simplejwt"
])

# Generate --collect-all arguments dynamically
collect_all_args = [f"--collect-all={imp}" for imp in collect_all_args]
# PyInstaller arguments
pyinstaller_args = \
    (
            [
                # "--onedir",
                "--onefile",
                "--console",
                "--clean",
                f"--add-data={BASE_DIR}/settings.py;django_qlktx",
                "start_app_with_ui.py",
                "--name=QLKTX",
                f"--runtime-hook={BASE_DIR}/hook-django.py",
                # f"--hidden-import={venv_path}",
                '--hidden-import=structlog',  # Make sure structlog is included
                # "--debug=all"

            ] + add_data_args + [f"--hidden-import={imp}" for imp in hidden_imports] + collect_all_args
    )

# [f"--hidden-import={imp}" for imp in hidden_imports] + collect_all_args
pyinstaller_args.append("--additional-hooks-dir=./django_qlktx")

# Run PyInstaller
PyInstaller.__main__.run(pyinstaller_args)
