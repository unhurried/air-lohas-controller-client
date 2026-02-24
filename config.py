import ujson as json
import urequests as requests


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


def _decode_text(payload):
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return str(payload)


def _convert_offset_to_adjust(value, field):
    offset = _require_int(value, field)
    if -2 <= offset <= 2:
        return offset + 2
    if 0 <= offset <= 4 or offset == 255:
        return offset
    raise ValueError(f"{field} must be -2..2 (or 0..4/255)")


def _extract_current_settings(raw):
    if not isinstance(raw, dict):
        raise ValueError("config must be a mapping")

    current = raw.get("currentSettings")
    if current is None:
        current = raw

    if not isinstance(current, dict):
        raise ValueError("currentSettings must be a mapping")

    return current


def _extract_current_settings_from_wrapped_response(raw):
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


def _decode_response_payload(response):
    json_func = getattr(response, "json", None)
    if json_func is not None:
        try:
            return json_func()
        except Exception:
            pass

    raw_text = getattr(response, "text", None)
    if raw_text is None:
        raw_text = getattr(response, "content", b"")
    return json.loads(_decode_text(raw_text))


def _load_config_mapping(raw):
    current = _extract_current_settings(raw)

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


def load_config_from_cloudflare_kv(
    account_id,
    namespace_id,
    api_token,
    key,
    timeout=10,
):
    account_id = _require_str(account_id, "account_id")
    namespace_id = _require_str(namespace_id, "namespace_id")
    api_token = _require_str(api_token, "api_token")
    key = _require_str(key, "key")

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        + account_id
        + "/storage/kv/namespaces/"
        + namespace_id
        + "/values/"
        + key
    )
    response = requests.get(
        url,
        headers={"Authorization": "Bearer " + api_token},
        timeout=timeout,
    )
    try:
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        raw = _decode_response_payload(response)
    finally:
        close = getattr(response, "close", None)
        if close is not None:
            close()

    normalized = _extract_current_settings_from_wrapped_response(raw)
    return _load_config_mapping(normalized)
