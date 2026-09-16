#!/usr/bin/env python
"""Командный файл Django для локального MVP."""

from pathlib import Path
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.web_mvp.web_mvp.settings")


def main() -> None:
    """Запускает команды Django."""
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
