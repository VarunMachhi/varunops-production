#!/usr/bin/env python
from pathlib import Path
import os
import sys

BASE_DIR = Path(__file__).resolve().parent
# Be explicit on Windows: always make the folder containing manage.py importable.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

project_settings = BASE_DIR / "varunops" / "settings.py"
if not project_settings.is_file():
    raise RuntimeError(
        f"VarunOps project files are incomplete. Missing: {project_settings}. "
        "Extract the whole ZIP to a normal folder before running setup."
    )

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "varunops.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
