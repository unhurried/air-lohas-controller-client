"""Tests for state module."""

from state import LoopState


class TestLoopState:
    """Tests for LoopState."""

    def test_initial_values(self):
        s = LoopState()
        assert s.last_process_time == 0
        assert s.last_settings is None

    def test_update(self):
        s = LoopState()
        settings = {"mode": "heat", "base_temp": 22, "rooms": {}}
        s.update(1000, settings)
        assert s.last_process_time == 1000
        assert s.last_settings == settings

    def test_multiple_updates(self):
        s = LoopState()
        s.update(100, {"mode": "heat"})
        s.update(200, {"mode": "auto-save"})
        assert s.last_process_time == 200
        assert s.last_settings["mode"] == "auto-save"
