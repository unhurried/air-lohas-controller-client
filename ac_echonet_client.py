"""ECHONET Lite power control client for aircon on/off.

Implements the ECHONET Lite protocol over UDP (port 3610) to send
SetC commands for the Operation Status property (EPC 0x80) of a
home air conditioner (EOJ class 0x0130).

Reference: ECHONET Lite AIF Specification for Home Air Conditioner
           (ac_aif_ver1.10)
"""

import usocket
import ubinascii
import utime

# ---------------------------------------------------------------------------
# ECHONET Lite constants
# ---------------------------------------------------------------------------

ECHONET_PORT = 3610

# ECHONET Lite header
_EHD1 = 0x10          # ECHONET Lite
_EHD2 = 0x81          # Format 1 (specified message format)

# Controller EOJ (SEOJ): Controller class (05FF01)
_CONTROLLER_EOJ = bytes([0x05, 0xFF, 0x01])

# ESV (ECHONET Lite Service)
_ESV_SETI = 0x60      # Property write (no response)

# Air conditioner properties (from AIF spec)
_EPC_OPERATION_STATUS = 0x80   # 動作状態
_EDT_ON = bytes([0x30])        # ON
_EDT_OFF = bytes([0x31])       # OFF


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------

def _parse_eoj(eoj_str):
    """Parse EOJ string like ``'0x013001'`` into 3 bytes."""
    s = eoj_str
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]
    if len(s) != 6:
        raise ValueError("EOJ must be 6 hex digits: " + eoj_str)
    return bytes([int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)])


def _build_frame(tid, seoj, deoj, esv, properties):
    """Build an ECHONET Lite frame (Format 1).

    Args:
        tid: Transaction ID (0-65535).
        seoj: Source EOJ (3 bytes).
        deoj: Destination EOJ (3 bytes).
        esv: Service code byte.
        properties: list of ``(epc, edt_bytes)`` tuples.

    Returns:
        ``bytes`` — the complete ECHONET Lite frame.
    """
    frame = bytearray()
    frame.append(_EHD1)
    frame.append(_EHD2)
    frame.append((tid >> 8) & 0xFF)
    frame.append(tid & 0xFF)
    frame.extend(seoj)
    frame.extend(deoj)
    frame.append(esv)
    frame.append(len(properties))          # OPC
    for epc, edt in properties:
        frame.append(epc)
        frame.append(len(edt))             # PDC
        frame.extend(edt)
    return bytes(frame)


# ---------------------------------------------------------------------------
# PowerClient
# ---------------------------------------------------------------------------

class AcEchonetClient:
    """Air Conditioner ECHONET Lite Client.

    Controls air conditioner power via the ECHONET Lite protocol over
    UDP (port 3610).  Sends SetI commands for EPC 0x80 (Operation
    Status) to turn the air conditioner on or off.

    Args:
        aircon_ip: IP address of the air conditioner.
        eoj: EOJ string, e.g. ``'0x013001'``.
        timeout: UDP receive timeout in seconds.
    """

    def __init__(self, aircon_ip, eoj="0x013001", timeout=15):
        self.aircon_ip = aircon_ip
        self.deoj = _parse_eoj(eoj)
        self.timeout = timeout
        self._tid = 0

    def _next_tid(self):
        self._tid = (self._tid + 1) & 0xFFFF
        return self._tid

    def _send_set(self, epc, edt):
        """Send a SetI (write, no response) command.

        Waits 5 seconds after sending to allow the device to process.
        """
        tid = self._next_tid()
        frame = _build_frame(
            tid, _CONTROLLER_EOJ, self.deoj, _ESV_SETI,
            [(epc, edt)],
        )

        print("[DEBUG] _send_set: target={}:{} tid=0x{:04x}".format(
            self.aircon_ip, ECHONET_PORT, tid))
        print("[DEBUG] _send_set: frame={}".format(
            ubinascii.hexlify(frame).decode()))
        print("[DEBUG] _send_set: DEOJ={} EPC=0x{:02x} EDT={}".format(
            ubinascii.hexlify(self.deoj).decode(), epc,
            ubinascii.hexlify(edt).decode()))

        sock = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
        try:
            sent = sock.sendto(frame, (self.aircon_ip, ECHONET_PORT))
            print("[DEBUG] _send_set: sent {} bytes".format(sent))
        finally:
            sock.close()

        print("[DEBUG] _send_set: waiting 5s for device to process...")
        utime.sleep(5)

    def power_on(self):
        """Turn the air conditioner ON (EPC 0x80 = 0x30)."""
        self._send_set(_EPC_OPERATION_STATUS, _EDT_ON)
        print("ECHONET Lite: power ON sent")

    def power_off(self):
        """Turn the air conditioner OFF (EPC 0x80 = 0x31)."""
        self._send_set(_EPC_OPERATION_STATUS, _EDT_OFF)
        print("ECHONET Lite: power OFF sent")
