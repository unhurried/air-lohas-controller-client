"""MicroPython compatibility shims for running tests on CPython.

This module installs fake/redirect modules into sys.modules so that
MicroPython-specific imports (ujson, urequests, usocket, utime, ubinascii,
ussl, network) resolve to CPython equivalents or mocks.

Import this module before importing any project module.
"""

import sys
import json
import socket
import time
import binascii
from unittest.mock import MagicMock

# ujson -> json (add separators support that ujson has)
sys.modules["ujson"] = json

# ubinascii -> binascii
sys.modules["ubinascii"] = binascii

# urequests -> mock (will be configured per-test)
_urequests_mock = MagicMock()
sys.modules["urequests"] = _urequests_mock

# usocket -> socket (with AF_INET, SOCK_DGRAM, SOCK_STREAM constants)
sys.modules["usocket"] = socket

# utime -> provide minimal MicroPython utime API
class _UTime:
    """Minimal utime shim mapping to CPython time module."""

    @staticmethod
    def ticks_ms():
        return int(time.time() * 1000)

    @staticmethod
    def ticks_diff(a, b):
        return a - b

    @staticmethod
    def sleep_ms(ms):
        time.sleep(ms / 1000)

    @staticmethod
    def sleep(s):
        time.sleep(s)

sys.modules["utime"] = _UTime()

# ussl -> mock
sys.modules["ussl"] = MagicMock()

# network -> mock
_network_mock = MagicMock()
_network_mock.STA_IF = 0
sys.modules["network"] = _network_mock

# hashlib — CPython hashlib already has md5.  Nothing to patch.
