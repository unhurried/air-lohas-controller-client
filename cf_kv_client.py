import ujson as json
import urequests as requests

from config import (
    build_current_settings_dict,
    build_current_settings_dict_mode_only,
    parse_kv_data,
    update_raw_data_current_settings,
    _require_str,
)
from ac_http_client import _json_dumps
from time_utils import parse_http_date


class KvResult:
    """Result of fetching config from Cloudflare KV."""

    def __init__(self, config, updated_at, process_time, raw_data):
        self.config = config          # Config object
        self.updated_at = updated_at  # Unix epoch seconds from updatedAt field
        self.process_time = process_time  # Unix epoch seconds from Date header
        self.raw_data = raw_data      # Original raw dict for write-back


def _decode_text(payload):
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return str(payload)


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


def _get_date_header(response):
    """Extract Date header from HTTP response and parse to epoch seconds."""
    headers = getattr(response, "headers", None)
    if headers is None:
        return 0
    date_str = headers.get("Date") or headers.get("date")
    if not date_str:
        return 0
    try:
        return parse_http_date(date_str)
    except Exception:
        return 0


def _kv_url(account_id, namespace_id, key):
    return (
        "https://api.cloudflare.com/client/v4/accounts/"
        + account_id
        + "/storage/kv/namespaces/"
        + namespace_id
        + "/values/"
        + key
    )


class CfKvClient:
    """Cloudflare Workers KV Client.

    Provides methods to fetch and update air conditioner configuration
    data stored in Cloudflare Workers KV.

    Args:
        account_id: Cloudflare account ID.
        namespace_id: KV namespace ID.
        api_token: Cloudflare API bearer token.
        key: KV key name.
        timeout: HTTP timeout in seconds.
    """

    def __init__(self, account_id, namespace_id, api_token, key, timeout=10):
        self.account_id = _require_str(account_id, "account_id")
        self.namespace_id = _require_str(namespace_id, "namespace_id")
        self.api_token = _require_str(api_token, "api_token")
        self.key = _require_str(key, "key")
        self.timeout = timeout

    def fetch_config(self):
        """Fetch config from Cloudflare KV.

        Returns:
            KvResult with config, updated_at, process_time, and raw_data.
        """
        url = _kv_url(self.account_id, self.namespace_id, self.key)
        response = requests.get(
            url,
            headers={"Authorization": "Bearer " + self.api_token},
            timeout=self.timeout,
        )
        try:
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            process_time = _get_date_header(response)
            raw = _decode_response_payload(response)
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()

        config, updated_at = parse_kv_data(raw)
        return KvResult(
            config=config,
            updated_at=updated_at,
            process_time=process_time,
            raw_data=raw,
        )

    def update_current_settings(
        self, raw_data, current_state, mode_only=False,
    ):
        """Write aircon settings back to KV, updating only currentSettings.

        Uses byte-length for Content-Length to handle multi-byte characters.

        Args:
            raw_data: Original raw KV data dict (from fetch_config).
            current_state: Aircon state dict with mode, base_temp,
                           room_names, room_adjust.
            mode_only: If True, only update mode and preserve existing
                       baseTemperature and roomOffsets in KV.
        """
        if mode_only:
            new_settings = build_current_settings_dict_mode_only(
                mode=current_state["mode"],
                raw_data=raw_data,
            )
        else:
            new_settings = build_current_settings_dict(
                mode=current_state["mode"],
                base_temp=current_state["base_temp"],
                room_names=current_state["room_names"],
                room_adjust=current_state["room_adjust"],
            )
        updated = update_raw_data_current_settings(raw_data, new_settings)

        body_str = _json_dumps(updated)
        body_bytes = body_str.encode("utf-8")

        url = _kv_url(self.account_id, self.namespace_id, self.key)
        response = requests.put(
            url,
            headers={
                "Authorization": "Bearer " + self.api_token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body_bytes)),
            },
            data=body_bytes,
            timeout=self.timeout,
        )
        try:
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()
