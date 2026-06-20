from time_utils import parse_iso_datetime


class Config:
    def __init__(self, mode, base_temp, rooms):
        self.mode = mode
        self.base_temp = base_temp
        self.rooms = rooms


def _require_str(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_int(value, field):
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _convert_offset_to_adjust(value, field):
    offset = _require_int(value, field)
    if -2 <= offset <= 2:
        return offset + 2
    if 0 <= offset <= 4 or offset == 255:
        return offset
    raise ValueError(f"{field} must be -2..2 (or 0..4/255)")


def _convert_adjust_to_offset(adjust):
    """Convert aircon adjust value (0-4 or 255) to KV offset (-2..2 or 255)."""
    if adjust == 255:
        return 255
    if 0 <= adjust <= 4:
        return adjust - 2
    raise ValueError(f"adjust must be 0-4 or 255, got {adjust}")


def _extract_current_settings(raw):
    if not isinstance(raw, dict):
        raise ValueError("config must be a mapping")

    current = raw.get("currentSettings")
    if current is None:
        current = raw

    if not isinstance(current, dict):
        raise ValueError("currentSettings must be a mapping")

    return current


def _normalize_wrapped_response(raw):
    if not isinstance(raw, dict):
        return raw

    for wrapper_key in ("result", "data", "value"):
        nested = raw.get(wrapper_key)
        if isinstance(nested, dict):
            if "currentSettings" in nested:
                return nested
            if "mode" in nested and "baseTemperature" in nested:
                return nested

    return raw


def _parse_config(current):
    """Parse a currentSettings dict into a Config object."""
    mode = _require_str(current.get("mode"), "currentSettings.mode")

    base_temp = _require_int(
        current.get("baseTemperature"),
        "currentSettings.baseTemperature",
    )

    raw_offsets = current.get("roomOffsets", {})
    if raw_offsets is None:
        raw_offsets = {}
    if not isinstance(raw_offsets, dict):
        raise ValueError("currentSettings.roomOffsets must be a mapping")

    rooms = {}
    for room_name, offset in raw_offsets.items():
        name = _require_str(room_name, "currentSettings.roomOffsets key")
        rooms[name] = _convert_offset_to_adjust(
            offset,
            f"currentSettings.roomOffsets[{name}]",
        )

    return Config(mode=mode, base_temp=base_temp, rooms=rooms)


def parse_kv_data(raw):
    """Parse raw KV JSON data into (Config, updated_at_epoch).

    Args:
        raw: Parsed JSON dict from KV response body.

    Returns:
        Tuple of (Config, updated_at) where updated_at is Unix epoch seconds.
    """
    normalized = _normalize_wrapped_response(raw)
    current = _extract_current_settings(normalized)
    config = _parse_config(current)

    updated_at = 0
    if isinstance(current, dict):
        updated_at_str = current.get("updatedAt")
        if updated_at_str:
            try:
                updated_at = parse_iso_datetime(updated_at_str)
            except Exception:
                updated_at = 0

    return config, updated_at


def build_current_settings_dict(mode, base_temp, room_names, room_adjust):
    """Build a currentSettings dict from aircon state for KV write-back.

    Args:
        mode: Mode string (e.g. 'auto-steady').
        base_temp: Base temperature integer.
        room_names: List of room name strings.
        room_adjust: List of adjust values (0-4 or 255).

    Returns:
        dict suitable for currentSettings in KV data.
    """
    offsets = {}
    for i, name in enumerate(room_names):
        if not name:
            continue
        if i >= len(room_adjust):
            continue
        offsets[name] = _convert_adjust_to_offset(room_adjust[i])

    return {
        "mode": mode,
        "baseTemperature": base_temp,
        "roomOffsets": offsets,
    }


def update_raw_data_current_settings(raw_data, new_current_settings):
    """Update currentSettings in raw KV data, preserving other fields.

    Args:
        raw_data: Original raw KV data dict.
        new_current_settings: New currentSettings dict.

    Returns:
        Updated raw data dict (shallow copy).
    """
    if "currentSettings" in raw_data:
        updated = dict(raw_data)
        updated["currentSettings"] = new_current_settings
        return updated

    for wrapper_key in ("result", "data", "value"):
        nested = raw_data.get(wrapper_key)
        if isinstance(nested, dict) and "currentSettings" in nested:
            updated = dict(raw_data)
            updated[wrapper_key] = dict(nested)
            updated[wrapper_key]["currentSettings"] = new_current_settings
            return updated

    raise ValueError("Cannot find currentSettings in raw data")


def build_current_settings_dict_mode_only(mode, raw_data):
    """Build currentSettings that only updates mode, preserving temps.

    Used when writing power-off state to KV: mode is set to '-' while
    baseTemperature and roomOffsets are kept from the existing KV data.

    Args:
        mode: New mode string (typically '-').
        raw_data: Original raw KV data dict.

    Returns:
        dict suitable for currentSettings in KV data.
    """
    normalized = _normalize_wrapped_response(raw_data)
    existing = _extract_current_settings(normalized)
    return {
        "mode": mode,
        "baseTemperature": existing.get("baseTemperature"),
        "roomOffsets": existing.get("roomOffsets"),
    }
