import os
import socket
import sys
import webbrowser
from multiprocessing import freeze_support, Process
from tkinter import Tk, Label, Button, Entry, StringVar, messagebox
from django.core.management import execute_from_command_line, call_command
from django.contrib.auth import get_user_model


def find_free_port(starting_port=8000):
    """Find an available port starting from the given port."""
    port = starting_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return port  # Port is free
        except OSError:
            OSError(f"Port {port} is already in use.")  # Raise error if port is in use


def create_default_superuser():
    """Create a default superuser if it doesn't already exist."""
    os.environ.setdefault("DJANGO_SUPERUSER_EMAIL", "admin@gmail.com")
    os.environ.setdefault("DJANGO_SUPERUSER_PASSWORD", "admin")
    os.environ.setdefault("DJANGO_SUPERUSER_USERNAME", "admin")

    User = get_user_model()

    # Ensure the superuser exists
    if not User.objects.filter(is_superuser=True).exists():
        print("Creating default superuser...")
        User.objects.create_superuser(
            email=os.environ["DJANGO_SUPERUSER_EMAIL"],
            username=os.environ["DJANGO_SUPERUSER_USERNAME"],
            password=os.environ["DJANGO_SUPERUSER_PASSWORD"],
        )
        print("Finish creating default superuser...")
    else:
        print("Default superuser already exists.")


def start_django_server(port):
    """Start the Django development server on the specified port."""
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_qlktx.settings")

        # Apply migrations before starting the server
        call_command('migrate', interactive=False)

        # Create a default superuser
        create_default_superuser()

        # Prepare the arguments for running the server
        sys.argv = ["manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"]

        # Open the Django admin page in the default web browser
        admin_url = f"http://127.0.0.1:{port}/admin"
        print(f"Opening Django admin interface at {admin_url}")
        webbrowser.open(admin_url)

        # Start the server
        execute_from_command_line(sys.argv)
    except Exception as e:
        print(f"An error occurred while starting the server: {e}")


def run_server_action():
    """Handler for the Run Server button."""
    try:
        free_port = find_free_port()

        # Start the Django server in a new process
        server_process = Process(target=start_django_server, args=(free_port,), daemon=True)
        server_process.start()

        # Inform the user that the server is running
        admin_url = f"http://127.0.0.1:{free_port}/admin"
        messagebox.showinfo(
            "Server Running",
            f"Django server is running on {admin_url}"
        )
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")


# Tkinter UI
def create_ui():
    root = Tk()
    root.title("Cửa sổ khởi động")
    root.geometry("500x300")

    Label(root, text="Màn hình khởi động ứng dụng ", font=("Arial", 16)).pack(pady=10)

    # Button to directly run the Django server
    Button(root, text="Chạy ứng dụng", command=run_server_action, width=20).pack(pady=10)

    # Entry for custom command
    command_var = StringVar()
    Label(root, text="Nhập câu lệnh").pack(pady=5)
    Entry(root, textvariable=command_var, width=50).pack(pady=5)

    # Button to run custom command
    Button(root, text="Chạy câu lệnh", command=lambda: run_django_command(command_var), width=20).pack(pady=10)

    # Quit Button
    Button(root, text="Thoát ra", command=root.quit, width=20, fg="red").pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_qlktx.settings")
    freeze_support()  # Required for multiprocessing in PyInstaller
    create_ui()
