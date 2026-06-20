"""Tests for ac_echonet_client module (ECHONET Lite power control).

All UDP socket communication is mocked  Eno real packets are sent.
"""

import pytest
from unittest.mock import patch, MagicMock

from ac_echonet_client import (
    AcEchonetClient,
    _parse_eoj,
    _build_frame,
    ECHONET_PORT,
    _EHD1,
    _EHD2,
    _ESV_SETI,
    _CONTROLLER_EOJ,
    _EPC_OPERATION_STATUS,
    _EDT_ON,
    _EDT_OFF,
)


def _parse_response(data):
    """Parse an ECHONET Lite frame for test verification."""
    if len(data) < 12:
        raise ValueError("ECHONET Lite frame too short: " + str(len(data)))
    if data[0] != _EHD1 or data[1] != _EHD2:
        raise ValueError("Not an ECHONET Lite Format 1 frame")

    tid = (data[2] << 8) | data[3]
    seoj = data[4:7]
    deoj = data[7:10]
    esv = data[10]
    opc = data[11]

    props = []
    offset = 12
    for _ in range(opc):
        if offset >= len(data):
            break
        epc = data[offset]
        pdc = data[offset + 1] if offset + 1 < len(data) else 0
        edt = data[offset + 2: offset + 2 + pdc]
        props.append((epc, edt))
        offset += 2 + pdc

    return {
        "tid": tid,
        "seoj": seoj,
        "deoj": deoj,
        "esv": esv,
        "properties": props,
    }


# ---------------------------------------------------------------------------
# _parse_eoj
# ---------------------------------------------------------------------------

class TestParseEoj:
    def test_with_0x_prefix(self):
        result = _parse_eoj("0x013001")
        assert result == bytes([0x01, 0x30, 0x01])

    def test_with_0X_prefix(self):
        result = _parse_eoj("0X013001")
        assert result == bytes([0x01, 0x30, 0x01])

    def test_without_prefix(self):
        result = _parse_eoj("013001")
        assert result == bytes([0x01, 0x30, 0x01])

    def test_invalid_length_raises(self):
        with pytest.raises(ValueError):
            _parse_eoj("0x01")

    def test_custom_eoj(self):
        result = _parse_eoj("0x05FF01")
        assert result == bytes([0x05, 0xFF, 0x01])


# ---------------------------------------------------------------------------
# _build_frame / _parse_response round-trip
# ---------------------------------------------------------------------------

class TestBuildAndParseFrame:
    def test_round_trip(self):
        """Build a frame and parse it back  Efields should match."""
        tid = 0x1234
        seoj = bytes([0x05, 0xFF, 0x01])
        deoj = bytes([0x01, 0x30, 0x01])
        esv = _ESV_SETI
        props = [(_EPC_OPERATION_STATUS, _EDT_ON)]

        frame = _build_frame(tid, seoj, deoj, esv, props)
        parsed = _parse_response(frame)

        assert parsed["tid"] == tid
        assert parsed["seoj"] == seoj
        assert parsed["deoj"] == deoj
        assert parsed["esv"] == esv
        assert len(parsed["properties"]) == 1
        assert parsed["properties"][0][0] == _EPC_OPERATION_STATUS
        assert parsed["properties"][0][1] == _EDT_ON

    def test_frame_header(self):
        """Verify EHD1, EHD2 are set correctly."""
        frame = _build_frame(1, _CONTROLLER_EOJ, bytes(3), _ESV_SETI, [])
        assert frame[0] == _EHD1
        assert frame[1] == _EHD2

    def test_multiple_properties(self):
        props = [
            (_EPC_OPERATION_STATUS, _EDT_ON),
            (0x81, bytes([0x01])),
        ]
        frame = _build_frame(1, _CONTROLLER_EOJ, bytes(3), _ESV_SETI, props)
        parsed = _parse_response(frame)
        assert len(parsed["properties"]) == 2

    def test_opc_count(self):
        """OPC byte should reflect the number of properties."""
        props = [(_EPC_OPERATION_STATUS, _EDT_ON)]
        frame = _build_frame(1, _CONTROLLER_EOJ, bytes(3), _ESV_SETI, props)
        opc_byte = frame[11]
        assert opc_byte == 1

    def test_parse_too_short_raises(self):
        with pytest.raises(ValueError):
            _parse_response(bytes(5))

    def test_parse_wrong_ehd_raises(self):
        bad = bytearray(12)
        bad[0] = 0xFF  # wrong EHD1
        with pytest.raises(ValueError):
            _parse_response(bytes(bad))


# ---------------------------------------------------------------------------
# AcEchonetClient (mocked socket)
# ---------------------------------------------------------------------------

class TestAcEchonetClient:
    """Test AcEchonetClient with mocked UDP socket."""

    @patch("ac_echonet_client.utime")
    @patch("ac_echonet_client.usocket")
    def test_power_on_sends_udp(self, mock_socket_mod, mock_utime):
        mock_sock = MagicMock()
        mock_socket_mod.socket.return_value = mock_sock
        mock_socket_mod.AF_INET = 2
        mock_socket_mod.SOCK_DGRAM = 2
        mock_sock.sendto.return_value = 14

        pc = AcEchonetClient(aircon_ip="192.168.1.50", eoj="0x013001")
        pc.power_on()

        mock_sock.sendto.assert_called_once()
        args = mock_sock.sendto.call_args[0]
        frame_bytes = args[0]
        addr = args[1]

        assert addr == ("192.168.1.50", ECHONET_PORT)

        # Verify it's a valid ECHONET Lite frame
        parsed = _parse_response(frame_bytes)
        assert parsed["esv"] == _ESV_SETI
        # Check EPC is operation status and EDT is ON
        epc, edt = parsed["properties"][0]
        assert epc == _EPC_OPERATION_STATUS
        assert edt == _EDT_ON

        mock_sock.close.assert_called_once()

    @patch("ac_echonet_client.utime")
    @patch("ac_echonet_client.usocket")
    def test_power_off_sends_udp(self, mock_socket_mod, mock_utime):
        mock_sock = MagicMock()
        mock_socket_mod.socket.return_value = mock_sock
        mock_socket_mod.AF_INET = 2
        mock_socket_mod.SOCK_DGRAM = 2
        mock_sock.sendto.return_value = 14

        pc = AcEchonetClient(aircon_ip="192.168.1.50", eoj="0x013001")
        pc.power_off()

        args = mock_sock.sendto.call_args[0]
        frame_bytes = args[0]
        parsed = _parse_response(frame_bytes)
        epc, edt = parsed["properties"][0]
        assert epc == _EPC_OPERATION_STATUS
        assert edt == _EDT_OFF

    @patch("ac_echonet_client.utime")
    @patch("ac_echonet_client.usocket")
    def test_tid_increments(self, mock_socket_mod, mock_utime):
        mock_sock = MagicMock()
        mock_socket_mod.socket.return_value = mock_sock
        mock_socket_mod.AF_INET = 2
        mock_socket_mod.SOCK_DGRAM = 2
        mock_sock.sendto.return_value = 14

        pc = AcEchonetClient(aircon_ip="192.168.1.50")
        pc.power_on()
        frame1 = mock_sock.sendto.call_args[0][0]
        pc.power_off()
        frame2 = mock_sock.sendto.call_args[0][0]

        tid1 = _parse_response(frame1)["tid"]
        tid2 = _parse_response(frame2)["tid"]
        assert tid2 == tid1 + 1

    @patch("ac_echonet_client.utime")
    @patch("ac_echonet_client.usocket")
    def test_socket_closed_even_on_error(self, mock_socket_mod, mock_utime):
        mock_sock = MagicMock()
        mock_socket_mod.socket.return_value = mock_sock
        mock_socket_mod.AF_INET = 2
        mock_socket_mod.SOCK_DGRAM = 2
        mock_sock.sendto.side_effect = OSError("send failed")

        pc = AcEchonetClient(aircon_ip="192.168.1.50")
        with pytest.raises(OSError):
            pc.power_on()
        mock_sock.close.assert_called_once()

    @patch("ac_echonet_client.utime")
    @patch("ac_echonet_client.usocket")
    def test_custom_eoj(self, mock_socket_mod, mock_utime):
        mock_sock = MagicMock()
        mock_socket_mod.socket.return_value = mock_sock
        mock_socket_mod.AF_INET = 2
        mock_socket_mod.SOCK_DGRAM = 2
        mock_sock.sendto.return_value = 14

        pc = AcEchonetClient(aircon_ip="10.0.0.1", eoj="0x013002")
        pc.power_on()

        frame = mock_sock.sendto.call_args[0][0]
        parsed = _parse_response(frame)
        assert parsed["deoj"] == bytes([0x01, 0x30, 0x02])

    @patch("ac_echonet_client.utime")
    @patch("ac_echonet_client.usocket")
    def test_deoj_set_from_eoj(self, mock_socket_mod, mock_utime):
        pc = AcEchonetClient(aircon_ip="10.0.0.1", eoj="0x013005")
        assert pc.deoj == bytes([0x01, 0x30, 0x05])

    @patch("ac_echonet_client.utime")
    @patch("ac_echonet_client.usocket")
    def test_seoj_is_controller(self, mock_socket_mod, mock_utime):
        """SEOJ should be the controller EOJ (05FF01)."""
        mock_sock = MagicMock()
        mock_socket_mod.socket.return_value = mock_sock
        mock_socket_mod.AF_INET = 2
        mock_socket_mod.SOCK_DGRAM = 2
        mock_sock.sendto.return_value = 14

        pc = AcEchonetClient(aircon_ip="10.0.0.1")
        pc.power_on()

        frame = mock_sock.sendto.call_args[0][0]
        parsed = _parse_response(frame)
        assert parsed["seoj"] == _CONTROLLER_EOJ
