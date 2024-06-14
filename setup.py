from cx_Freeze import setup, Executable
import re


def parse_requirements(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    return [line.strip() for line in lines if not line.startswith('#')]  # Remove comments


def get_package_names(requirements):
    packages = []
    for req in requirements:
        # Extract package name using regex (adapt if needed)
        match = re.search(r"(?<=^- )([^ ]+)", req)
        if match:
            packages.append(match.group(1))
    return packages


requirements_path = "requirements.txt"  # Adjust path as needed
requirements = parse_requirements(requirements_path)
packages_to_include = get_package_names(requirements)

# Replace 'your_app_name' with the actual name of your Django app
build_exe_options = {
    "build_exe": f"build/manage.py",
    "excludes": [],
    "includes": packages_to_include,
    # "zip_include_packages": '*',
    'optimize': 1,
    'include_files': [
        'manage.py',
        "templates/",
        "static/",
        "media/",
        "core/",
        "django_qlktx/",
        "backend/",
    ],
    'silent_level': 1
}
executables = [Executable('manage.py')]

setup(
    name='Your Django App',
    version='1.0',
    description='Your Django Application Description',
    author='Your Name',
    options={"build_exe": build_exe_options},
    executables=executables
)
