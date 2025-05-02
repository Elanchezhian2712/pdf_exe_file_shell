import os
import sys
import django
from django.core.management import execute_from_command_line
import time
import importlib
import traceback

def get_app_root():
    if getattr(sys, 'frozen', False):
        executable_path = sys.executable
        app_root = os.path.dirname(executable_path)
        print(f"[run_backend.py] Running frozen. sys.executable: {executable_path}")
        print(f"[run_backend.py] Determined app root (dirname): {app_root}")
        return app_root
    else:
        script_path = os.path.abspath(__file__)
        app_root = os.path.dirname(script_path)
        print(f"[run_backend.py] Running as script. __file__: {script_path}")
        print(f"[run_backend.py] Determined app root (dirname): {app_root}")
        return app_root

APP_ROOT = get_app_root()
IS_FROZEN = getattr(sys, 'frozen', False) 

APP_DATA_PATH = os.environ.get('APP_DATA_PATH')

if APP_DATA_PATH:
    try:
        os.makedirs(APP_DATA_PATH, exist_ok=True)
        DATABASE_PATH = os.path.join(APP_DATA_PATH, 'db.sqlite3')
        print(f"[run_backend.py] Using database path: {DATABASE_PATH}")
    except OSError as e:
        print(f"[run_backend.py] ERROR: Could not create user data directory {APP_DATA_PATH}: {e}", file=sys.stderr)
        DATABASE_PATH = os.path.join(APP_ROOT, 'db.sqlite3')
        print(f"[run_backend.py] Falling back to database path: {DATABASE_PATH}", file=sys.stderr)
else:
    print("[run_backend.py] WARNING: APP_DATA_PATH not set. Using local db.sqlite3.", file=sys.stderr)
    DATABASE_PATH = os.path.join(APP_ROOT, 'db.sqlite3')


DJANGO_SETTINGS_MODULE = 'backend.settings' 
os.environ.setdefault('DJANGO_SETTINGS_MODULE', DJANGO_SETTINGS_MODULE)

try:
    settings_module = importlib.import_module(DJANGO_SETTINGS_MODULE)
    print(f"[run_backend.py] Imported settings module: {DJANGO_SETTINGS_MODULE}")

    settings_module.DATABASES['default']['NAME'] = DATABASE_PATH
    print(f"[run_backend.py] Overrode DATABASES['default']['NAME'] to: {DATABASE_PATH}")

    if IS_FROZEN:
        print("[run_backend.py] Application is frozen. Modifying Template/Static paths.")

        bundled_templates_dir = os.path.join(APP_ROOT, '_internal', 'templates')
        print(f"[run_backend.py] (Frozen) Calculated target bundled templates path: {bundled_templates_dir}")

        if os.path.exists(bundled_templates_dir):
            print(f"[run_backend.py] Bundled templates directory target EXISTS: {bundled_templates_dir}")
            if hasattr(settings_module, 'TEMPLATES') and isinstance(settings_module.TEMPLATES, list) and len(settings_module.TEMPLATES) > 0:
                settings_module.TEMPLATES[0]['DIRS'] = [bundled_templates_dir]
                settings_module.TEMPLATES[0]['APP_DIRS'] = False
                print(f"[run_backend.py] REPLACED TEMPLATES[0]['DIRS'] = [{bundled_templates_dir}]")
                print(f"[run_backend.py] Set TEMPLATES[0]['APP_DIRS'] = False")
            else: print("[run_backend.py] WARNING: Could not modify TEMPLATES setting structure.", file=sys.stderr)
        else:
            print(f"[run_backend.py] Bundled templates directory target DOES NOT EXIST: {bundled_templates_dir}")


        bundled_static_dir = os.path.join(APP_ROOT, '_internal', 'static')
        print(f"[run_backend.py] (Frozen) Calculated target bundled static path: {bundled_static_dir}")

        if os.path.exists(bundled_static_dir):
             print(f"[run_backend.py] Bundled static directory target EXISTS: {bundled_static_dir}")
             settings_module.STATICFILES_DIRS = [bundled_static_dir]
             print(f"[run_backend.py] REPLACED STATICFILES_DIRS = [{bundled_static_dir}]")
        else:
             print(f"[run_backend.py] Bundled static directory target DOES NOT EXIST: {bundled_static_dir}")
             settings_module.STATICFILES_DIRS = []
             print(f"[run_backend.py] Set STATICFILES_DIRS = []")

    else: 
        print("[run_backend.py] Application not frozen. Using default settings for Templates/Static.")


except ImportError as e:
     print(f"[run_backend.py] ERROR: Could not import settings module '{DJANGO_SETTINGS_MODULE}': {e}", file=sys.stderr)
     traceback.print_exc(file=sys.stderr)
     sys.exit(1)
except Exception as e:
     print(f"[run_backend.py] ERROR: Failed to modify settings module '{DJANGO_SETTINGS_MODULE}': {e}", file=sys.stderr)
     traceback.print_exc(file=sys.stderr)
     sys.exit(1)


def run_command(args):
    try:
        print(f"[run_backend.py] Executing command: {' '.join(args)}")
        execute_from_command_line([sys.argv[0]] + args)
        print(f"[run_backend.py] Command {' '.join(args)} finished successfully.")
        return 0
    except Exception as e:
        print(f"[run_backend.py] Error executing command {' '.join(args)}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "runserver"
    print(f"[run_backend.py] Received command: {command}")

    try:
        print("[run_backend.py] Calling django.setup()...")
        django.setup()
        print("[run_backend.py] Django setup complete.")
    except Exception as e:
        print(f"[run_backend.py] ERROR during django.setup(): {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    exit_code = 1
    if command == "migrate":
        exit_code = run_command(['migrate', '--noinput'])
    elif command == "runserver":
        exit_code = run_command(['runserver', '0.0.0.0:8000', '--noreload'])
    else:
        print(f"[run_backend.py] ERROR: Unknown command: {command}", file=sys.stderr)
        exit_code = 1

    print(f"[run_backend.py] Exiting with code {exit_code}")
    sys.exit(exit_code)