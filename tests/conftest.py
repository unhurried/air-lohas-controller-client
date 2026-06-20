"""Shared pytest fixtures and automatic MicroPython compatibility setup."""

import sys
import os

# Ensure the MicroPython compat shims are loaded before any project import.
# This must happen as early as possible.
import tests.micropython_compat  # noqa: F401

# Add project root to sys.path so that bare imports like `from client import ...`
# resolve correctly.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
