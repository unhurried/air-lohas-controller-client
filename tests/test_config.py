"""Tests for config module."""

import pytest
from config import (
    Config,
    parse_kv_data,
    build_current_settings_dict,
    update_raw_data_current_settings,
    build_current_settings_dict_mode_only,
    _convert_offset_to_adjust,
    _convert_adjust_to_offset,
    _require_str,
    _require_int,
    _extract_current_settings,
    _normalize_wrapped_response,
    _parse_config,
)


# ---------------------------------------------------------------------------
# _convert_offset_to_adjust / _convert_adjust_to_offset
# ---------------------------------------------------------------------------

class TestOffsetAdjustConversion:
    """Test offset <-> adjust conversion."""

    @pytest.mark.parametrize("offset,expected", [
        (-2, 0), (-1, 1), (0, 2), (1, 3), (2, 4),
    ])
    def test_offset_to_adjust(self, offset, expected):
        assert _convert_offset_to_adjust(offset, "test") == expected

    def test_offset_to_adjust_255(self):
        assert _convert_offset_to_adjust(255, "test") == 255

    @pytest.mark.parametrize("value,expected", [(3, 3), (4, 4)])
    def test_offset_to_adjust_pass_through_large(self, value, expected):
        """Values 3-4 fall through to the 0-4 range check and pass as-is."""
        assert _convert_offset_to_adjust(value, "test") == expected

    @pytest.mark.parametrize("value,expected", [(0, 2), (1, 3), (2, 4)])
    def test_offset_to_adjust_small_values_treated_as_offset(self, value, expected):
        """Values 0-2 match -2..2 range first, so they are treated as offsets."""
        assert _convert_offset_to_adjust(value, "test") == expected

    def test_offset_to_adjust_invalid(self):
        with pytest.raises(ValueError):
            _convert_offset_to_adjust(10, "test")

    @pytest.mark.parametrize("adjust,expected", [
        (0, -2), (1, -1), (2, 0), (3, 1), (4, 2),
    ])
    def test_adjust_to_offset(self, adjust, expected):
        assert _convert_adjust_to_offset(adjust) == expected

    def test_adjust_to_offset_255(self):
        assert _convert_adjust_to_offset(255) == 255

    def test_adjust_to_offset_invalid(self):
        with pytest.raises(ValueError):
            _convert_adjust_to_offset(10)


# ---------------------------------------------------------------------------
# _require_str / _require_int
# ---------------------------------------------------------------------------

class TestRequireHelpers:
    def test_require_str_ok(self):
        assert _require_str("hello", "f") == "hello"

    def test_require_str_empty_raises(self):
        with pytest.raises(ValueError):
            _require_str("", "f")

    def test_require_str_none_raises(self):
        with pytest.raises(ValueError):
            _require_str(None, "f")

    def test_require_int_ok(self):
        assert _require_int(42, "f") == 42

    def test_require_int_str_raises(self):
        with pytest.raises(ValueError):
            _require_int("42", "f")


# ---------------------------------------------------------------------------
# parse_kv_data
# ---------------------------------------------------------------------------

class TestParseKvData:
    """Test parsing of KV JSON data into Config."""

    def _make_raw(self, mode="auto-steady", base_temp=22, offsets=None,
                  updated_at=None):
        cs = {
            "mode": mode,
            "baseTemperature": base_temp,
            "roomOffsets": offsets or {},
        }
        if updated_at:
            cs["updatedAt"] = updated_at
        return {"currentSettings": cs}

    def test_basic_parse(self):
        raw = self._make_raw(
            mode="auto-steady",
            base_temp=22,
            offsets={"リビング": 0, "寝室": -1},
        )
        config, updated_at = parse_kv_data(raw)
        assert config.mode == "auto-steady"
        assert config.base_temp == 22
        assert "リビング" in config.rooms
        assert "寝室" in config.rooms
        assert updated_at == 0  # no updatedAt field

    def test_with_updated_at(self):
        raw = self._make_raw(updated_at="2026-02-25T11:04:41.596Z")
        config, updated_at = parse_kv_data(raw)
        # _to_unix_epoch uses day-inclusive counting (+86400 offset)
        assert updated_at == 1772103881

    def test_power_off_mode(self):
        raw = self._make_raw(mode="-")
        config, _ = parse_kv_data(raw)
        assert config.mode == "-"

    def test_auto_save_mode(self):
        raw = self._make_raw(mode="auto-save")
        config, _ = parse_kv_data(raw)
        assert config.mode == "auto-save"

    def test_room_offsets_converted_to_adjust(self):
        raw = self._make_raw(offsets={"Room1": -2, "Room2": 2, "Room3": 255})
        config, _ = parse_kv_data(raw)
        assert config.rooms["Room1"] == 0   # -2 -> adjust 0
        assert config.rooms["Room2"] == 4   # +2 -> adjust 4
        assert config.rooms["Room3"] == 255

    def test_wrapped_in_result(self):
        inner = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 20,
                "roomOffsets": {},
            }
        }
        raw = {"result": inner}
        config, _ = parse_kv_data(raw)
        assert config.mode == "auto-steady"
        assert config.base_temp == 20

    def test_flat_settings(self):
        """currentSettings keys at top level."""
        raw = {
            "mode": "auto-save",
            "baseTemperature": 25,
            "roomOffsets": {"A": 0},
        }
        config, _ = parse_kv_data(raw)
        assert config.mode == "auto-save"
        assert config.base_temp == 25

    def test_missing_mode_raises(self):
        raw = {"currentSettings": {"baseTemperature": 20, "roomOffsets": {}}}
        with pytest.raises(ValueError):
            parse_kv_data(raw)

    def test_missing_base_temp_raises(self):
        raw = {"currentSettings": {"mode": "auto-steady", "roomOffsets": {}}}
        with pytest.raises(ValueError):
            parse_kv_data(raw)


# ---------------------------------------------------------------------------
# build_current_settings_dict
# ---------------------------------------------------------------------------

class TestBuildCurrentSettingsDict:
    def test_basic_build(self):
        result = build_current_settings_dict(
            mode="auto-steady",
            base_temp=22,
            room_names=["リビング", "寝室", ""],
            room_adjust=[2, 3, 0],
        )
        assert result["mode"] == "auto-steady"
        assert result["baseTemperature"] == 22
        assert result["roomOffsets"]["リビング"] == 0   # adjust 2 -> offset 0
        assert result["roomOffsets"]["寝室"] == 1        # adjust 3 -> offset 1
        assert "" not in result["roomOffsets"]  # empty names skipped

    def test_room_adjust_255(self):
        result = build_current_settings_dict(
            mode="auto-save",
            base_temp=20,
            room_names=["Room1"],
            room_adjust=[255],
        )
        assert result["roomOffsets"]["Room1"] == 255

    def test_empty_rooms(self):
        result = build_current_settings_dict(
            mode="auto-steady",
            base_temp=22,
            room_names=[],
            room_adjust=[],
        )
        assert result["roomOffsets"] == {}


# ---------------------------------------------------------------------------
# update_raw_data_current_settings
# ---------------------------------------------------------------------------

class TestUpdateRawDataCurrentSettings:
    def test_top_level_current_settings(self):
        raw = {
            "currentSettings": {"mode": "old"},
            "otherField": "keep",
        }
        new_cs = {"mode": "new"}
        result = update_raw_data_current_settings(raw, new_cs)
        assert result["currentSettings"]["mode"] == "new"
        assert result["otherField"] == "keep"
        # Original not mutated
        assert raw["currentSettings"]["mode"] == "old"

    def test_nested_in_result(self):
        raw = {
            "result": {
                "currentSettings": {"mode": "old"},
                "meta": "data",
            }
        }
        new_cs = {"mode": "new"}
        result = update_raw_data_current_settings(raw, new_cs)
        assert result["result"]["currentSettings"]["mode"] == "new"
        assert result["result"]["meta"] == "data"

    def test_no_current_settings_raises(self):
        raw = {"foo": "bar"}
        with pytest.raises(ValueError):
            update_raw_data_current_settings(raw, {})


# ---------------------------------------------------------------------------
# build_current_settings_dict_mode_only
# ---------------------------------------------------------------------------

class TestBuildCurrentSettingsDictModeOnly:
    def test_preserves_temps(self):
        raw = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 22,
                "roomOffsets": {"Room1": 0},
            }
        }
        result = build_current_settings_dict_mode_only("-", raw)
        assert result["mode"] == "-"
        assert result["baseTemperature"] == 22
        assert result["roomOffsets"] == {"Room1": 0}
