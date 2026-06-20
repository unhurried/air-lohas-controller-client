"""Tests for sync module (sync loop logic).

All external I/O (aircon client, power client, KV) is mocked.
"""

import pytest
from unittest.mock import patch, MagicMock

from config import Config
from state import LoopState
from cf_kv_client import KvResult
from sync import (
    is_power_off,
    settings_differ,
    settings_from_aircon,
    settings_from_config,
    find_changed_rooms,
    build_adjust_from_current,
    apply_kv_to_aircon,
    run_once,
    MODE_POWER_OFF,
)


# ---------------------------------------------------------------------------
# is_power_off
# ---------------------------------------------------------------------------

class TestIsPowerOff:
    def test_dash_is_power_off(self):
        assert is_power_off("-") is True

    def test_auto_steady_not_off(self):
        assert is_power_off("auto-steady") is False

    def test_auto_save_not_off(self):
        assert is_power_off("auto-save") is False

    def test_none_not_off(self):
        assert is_power_off(None) is False


# ---------------------------------------------------------------------------
# settings_differ
# ---------------------------------------------------------------------------

class TestSettingsDiffer:
    def _config(self, mode="auto-steady", base_temp=22, rooms=None):
        return Config(mode=mode, base_temp=base_temp, rooms=rooms or {})

    def test_same_settings(self):
        current = {
            "mode": "auto-steady",
            "base_temp": 22,
            "room_names": ["Room1"],
            "room_adjust": [2],
        }
        config = self._config(rooms={"Room1": 2})
        assert settings_differ(current, config) is False

    def test_mode_differs(self):
        current = {
            "mode": "auto-steady",
            "base_temp": 22,
            "room_names": [],
            "room_adjust": [],
        }
        config = self._config(mode="auto-save")
        assert settings_differ(current, config) is True

    def test_base_temp_differs(self):
        current = {
            "mode": "auto-steady",
            "base_temp": 22,
            "room_names": [],
            "room_adjust": [],
        }
        config = self._config(base_temp=24)
        assert settings_differ(current, config) is True

    def test_room_adjust_differs(self):
        current = {
            "mode": "auto-steady",
            "base_temp": 22,
            "room_names": ["Room1"],
            "room_adjust": [2],
        }
        config = self._config(rooms={"Room1": 3})
        assert settings_differ(current, config) is True

    def test_power_off_ignores_temp(self):
        """When aircon is off, temp differences are ignored."""
        current = {
            "mode": "-",
            "base_temp": 22,
            "room_names": ["Room1"],
            "room_adjust": [2],
        }
        config = self._config(mode="-", base_temp=30, rooms={"Room1": 4})
        assert settings_differ(current, config) is False

    def test_none_mode_skipped(self):
        current = {
            "mode": None,
            "base_temp": 22,
            "room_names": [],
            "room_adjust": [],
        }
        config = self._config()
        assert settings_differ(current, config) is False

    def test_none_base_temp_skipped(self):
        current = {
            "mode": "auto-steady",
            "base_temp": None,
            "room_names": [],
            "room_adjust": [],
        }
        config = self._config(base_temp=30)
        assert settings_differ(current, config) is False

    def test_unknown_room_in_config(self):
        """Room in config but not in aircon is not flagged as different."""
        current = {
            "mode": "auto-steady",
            "base_temp": 22,
            "room_names": ["Room1"],
            "room_adjust": [2],
        }
        config = self._config(rooms={"Room1": 2, "Room2": 3})
        # Room2 not in current -> skipped in comparison
        assert settings_differ(current, config) is False


# ---------------------------------------------------------------------------
# settings_from_aircon / settings_from_config
# ---------------------------------------------------------------------------

class TestSettingsConversion:
    def test_settings_from_aircon(self):
        current = {
            "mode": "auto-steady",
            "base_temp": 22,
            "room_names": ["Room1", "", "Room3"],
            "room_adjust": [2, 0, 3],
        }
        result = settings_from_aircon(current)
        assert result["mode"] == "auto-steady"
        assert result["base_temp"] == 22
        assert "Room1" in result["rooms"]
        assert "" not in result["rooms"]  # empty names skipped
        assert "Room3" in result["rooms"]

    def test_settings_from_config(self):
        config = Config(
            mode="auto-save",
            base_temp=24,
            rooms={"A": 1, "B": 3},
        )
        result = settings_from_config(config)
        assert result["mode"] == "auto-save"
        assert result["base_temp"] == 24
        assert result["rooms"] == {"A": 1, "B": 3}


# ---------------------------------------------------------------------------
# find_changed_rooms
# ---------------------------------------------------------------------------

class TestFindChangedRooms:
    def test_no_changes(self):
        result = find_changed_rooms(
            ["Room1", "Room2"], [2, 3], {"Room1": 2, "Room2": 3},
        )
        assert result == []

    def test_one_changed(self):
        result = find_changed_rooms(
            ["Room1", "Room2"], [2, 3], {"Room1": 2, "Room2": 4},
        )
        assert result == ["Room2"]

    def test_unknown_room(self):
        """Room in desired but not in current is reported as changed."""
        result = find_changed_rooms(
            ["Room1"], [2], {"Room1": 2, "Room3": 1},
        )
        assert "Room3" in result

    def test_empty(self):
        result = find_changed_rooms([], [], {})
        assert result == []


# ---------------------------------------------------------------------------
# build_adjust_from_current
# ---------------------------------------------------------------------------

class TestBuildAdjustFromCurrent:
    def test_basic_merge(self):
        current = {
            "room_names": ["Room1", "Room2", "Room3"],
            "room_adjust": [2, 2, 2],
        }
        updates = {"Room2": 4}
        result = build_adjust_from_current(current, updates)
        assert result == [2, 4, 2]

    def test_multiple_updates(self):
        current = {
            "room_names": ["A", "B", "C"],
            "room_adjust": [0, 0, 0],
        }
        updates = {"A": 1, "C": 3}
        result = build_adjust_from_current(current, updates)
        assert result == [1, 0, 3]

    def test_unknown_room_raises(self):
        current = {
            "room_names": ["A"],
            "room_adjust": [0],
        }
        with pytest.raises(ValueError):
            build_adjust_from_current(current, {"Z": 1})

    def test_does_not_mutate_original(self):
        current = {
            "room_names": ["A", "B"],
            "room_adjust": [0, 0],
        }
        build_adjust_from_current(current, {"A": 3})
        assert current["room_adjust"] == [0, 0]


# ---------------------------------------------------------------------------
# apply_kv_to_aircon
# ---------------------------------------------------------------------------

class TestApplyKvToAircon:
    def _make_current(self, mode="auto-steady", base_temp=22,
                      room_names=None, room_adjust=None):
        return {
            "mode": mode,
            "base_temp": base_temp,
            "room_names": room_names or [],
            "room_adjust": room_adjust or [],
        }

    def test_power_off(self):
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(mode="auto-steady")
        config = Config(mode="-", base_temp=22, rooms={})

        apply_kv_to_aircon(client, power_client, current, config)

        power_client.power_off.assert_called_once()
        power_client.power_on.assert_not_called()
        # No mode/temp setting calls
        client.set_auto_steady.assert_not_called()
        client.set_base_temp.assert_not_called()

    def test_power_off_already_off(self):
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(mode="-")
        config = Config(mode="-", base_temp=22, rooms={})

        apply_kv_to_aircon(client, power_client, current, config)

        power_client.power_off.assert_not_called()  # already off

    def test_power_on_from_off(self):
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(
            mode="-",
            room_names=["Room1"],
            room_adjust=[2],
        )
        config = Config(
            mode="auto-steady",
            base_temp=22,
            rooms={"Room1": 3},
        )

        apply_kv_to_aircon(client, power_client, current, config)

        power_client.power_on.assert_called_once()
        client.set_auto_steady.assert_called_once()
        client.set_base_temp.assert_called_once_with(22)
        client.set_room_adjust.assert_called_once()

    def test_mode_change_auto_steady_to_save(self):
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(mode="auto-steady")
        config = Config(mode="auto-save", base_temp=22, rooms={})

        apply_kv_to_aircon(client, power_client, current, config)

        client.set_auto_save.assert_called_once()
        power_client.power_on.assert_not_called()
        power_client.power_off.assert_not_called()

    def test_base_temp_change(self):
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(mode="auto-steady", base_temp=20)
        config = Config(mode="auto-steady", base_temp=24, rooms={})

        apply_kv_to_aircon(client, power_client, current, config)

        client.set_base_temp.assert_called_once_with(24)

    def test_room_offsets_change(self):
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(
            mode="auto-steady",
            room_names=["A", "B"],
            room_adjust=[2, 2],
        )
        config = Config(
            mode="auto-steady",
            base_temp=22,
            rooms={"A": 2, "B": 4},
        )

        apply_kv_to_aircon(client, power_client, current, config)

        client.set_room_adjust.assert_called_once_with([2, 4])

    def test_no_changes_needed(self):
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(
            mode="auto-steady",
            base_temp=22,
            room_names=["A"],
            room_adjust=[2],
        )
        config = Config(
            mode="auto-steady",
            base_temp=22,
            rooms={"A": 2},
        )

        apply_kv_to_aircon(client, power_client, current, config)

        # Nothing should change
        power_client.power_on.assert_not_called()
        power_client.power_off.assert_not_called()
        client.set_base_temp.assert_not_called()
        client.set_room_adjust.assert_not_called()

    def test_power_off_with_none_mode(self):
        """When current mode is None, power off is skipped."""
        client = MagicMock()
        power_client = MagicMock()
        current = self._make_current(mode=None)
        config = Config(mode="-", base_temp=22, rooms={})

        apply_kv_to_aircon(client, power_client, current, config)

        power_client.power_off.assert_not_called()


# ---------------------------------------------------------------------------
# run_once (integration test with all mocks)
# ---------------------------------------------------------------------------

class TestRunOnce:
    """Test full sync iteration with mocked I/O."""

    def _make_kv_result(self, mode="auto-steady", base_temp=22,
                        rooms=None, updated_at=1000, process_time=2000):
        config = Config(
            mode=mode,
            base_temp=base_temp,
            rooms=rooms or {},
        )
        raw_data = {
            "currentSettings": {
                "mode": mode,
                "baseTemperature": base_temp,
                "roomOffsets": rooms or {},
            }
        }
        return KvResult(
            config=config,
            updated_at=updated_at,
            process_time=process_time,
            raw_data=raw_data,
        )

    def _make_current(self, mode="auto-steady", base_temp=22,
                      room_names=None, room_adjust=None):
        return {
            "mode": mode,
            "base_temp": base_temp,
            "room_names": room_names or [],
            "room_adjust": room_adjust or [],
        }

    def test_no_diff_no_action(self):
        """When settings match, no aircon commands and no KV writes."""
        client = MagicMock()
        client.get_current_state.return_value = self._make_current()
        power_client = MagicMock()

        kv_client = MagicMock()
        kv_client.fetch_config.return_value = self._make_kv_result()

        state = LoopState()

        run_once(state, client, power_client, kv_client)

        # No aircon commands
        client.set_auto_steady.assert_not_called()
        client.set_auto_save.assert_not_called()
        client.set_base_temp.assert_not_called()
        power_client.power_on.assert_not_called()
        power_client.power_off.assert_not_called()

        # State updated
        assert state.last_process_time == 2000

    def test_kv_newer_applies_to_aircon(self):
        """When KV is newer, KV settings are applied to aircon."""
        client = MagicMock()
        client.get_current_state.return_value = self._make_current(
            base_temp=20,  # different from KV
        )
        power_client = MagicMock()

        kv_result = self._make_kv_result(
            base_temp=24,
            updated_at=5000,
            process_time=6000,
        )
        kv_client = MagicMock()
        kv_client.fetch_config.return_value = kv_result

        state = LoopState()
        state.last_process_time = 1000  # KV updated_at > this

        run_once(state, client, power_client, kv_client)

        # Base temp should be applied
        client.set_base_temp.assert_called_once_with(24)
        # KV should NOT be updated (KV -> aircon direction)
        kv_client.update_current_settings.assert_not_called()

    def test_aircon_newer_updates_kv(self):
        """When aircon is newer, aircon settings are written to KV."""
        client = MagicMock()
        client.get_current_state.return_value = self._make_current(
            base_temp=20,  # different from KV
        )
        power_client = MagicMock()

        kv_result = self._make_kv_result(
            base_temp=24,
            updated_at=500,    # older than last_process_time
            process_time=6000,
        )
        kv_client = MagicMock()
        kv_client.fetch_config.return_value = kv_result

        state = LoopState()
        state.last_process_time = 1000  # KV updated_at <= this

        run_once(state, client, power_client, kv_client)

        # KV should be updated with aircon settings
        kv_client.update_current_settings.assert_called_once()
        # Aircon settings should NOT be changed
        client.set_base_temp.assert_not_called()

    def test_power_off_from_kv(self):
        """KV says power off -> aircon is turned off."""
        client = MagicMock()
        client.get_current_state.return_value = self._make_current(
            mode="auto-steady",
        )
        power_client = MagicMock()

        kv_result = self._make_kv_result(
            mode="-",
            updated_at=5000,
            process_time=6000,
        )
        kv_client = MagicMock()
        kv_client.fetch_config.return_value = kv_result

        state = LoopState()
        state.last_process_time = 1000

        run_once(state, client, power_client, kv_client)

        power_client.power_off.assert_called_once()

    def test_state_updated_after_sync(self):
        """State is always updated with process_time and settings."""
        client = MagicMock()
        client.get_current_state.return_value = self._make_current()
        power_client = MagicMock()

        kv_client = MagicMock()
        kv_client.fetch_config.return_value = self._make_kv_result(process_time=9999)

        state = LoopState()

        run_once(state, client, power_client, kv_client)

        assert state.last_process_time == 9999
        assert state.last_settings is not None
