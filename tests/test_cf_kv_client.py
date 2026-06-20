"""Tests for cf_kv_client module.

All HTTP communication is mocked — no real Cloudflare API calls are made.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from ac_http_client import _json_dumps
from cf_kv_client import (
    CfKvClient,
    KvResult,
    _kv_url,
    _decode_text,
    _get_date_header,
)


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

class TestKvUrl:
    def test_url_format(self):
        result = _kv_url("acct123", "ns456", "mykey")
        assert result == (
            "https://api.cloudflare.com/client/v4/accounts/"
            "acct123/storage/kv/namespaces/ns456/values/mykey"
        )


class TestDecodeText:
    def test_bytes(self):
        assert _decode_text(b"hello") == "hello"

    def test_str(self):
        assert _decode_text("hello") == "hello"

    def test_int(self):
        assert _decode_text(123) == "123"


class TestGetDateHeader:
    def test_with_date_header(self):
        resp = MagicMock()
        resp.headers = {"Date": "Thu, 27 Feb 2026 12:00:00 GMT"}
        result = _get_date_header(resp)
        assert result == 1772280000

    def test_lowercase_date_header(self):
        resp = MagicMock()
        resp.headers = {"date": "Thu, 27 Feb 2026 12:00:00 GMT"}
        result = _get_date_header(resp)
        assert result == 1772280000

    def test_no_headers(self):
        resp = MagicMock()
        resp.headers = None
        assert _get_date_header(resp) == 0

    def test_no_date_field(self):
        resp = MagicMock()
        resp.headers = {"Content-Type": "application/json"}
        assert _get_date_header(resp) == 0

    def test_malformed_date(self):
        resp = MagicMock()
        resp.headers = {"Date": "not-a-date"}
        assert _get_date_header(resp) == 0


class TestJsonDumps:
    def test_dict(self):
        result = _json_dumps({"a": 1})
        parsed = json.loads(result)
        assert parsed == {"a": 1}


# ---------------------------------------------------------------------------
# CfKvClient.fetch_config (mocked HTTP)
# ---------------------------------------------------------------------------

class TestFetchConfig:
    """Test CfKvClient.fetch_config with mocked urequests."""

    def _mock_response(self, json_data, status_code=200, date_header=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status = MagicMock()
        resp.close = MagicMock()
        headers = {}
        if date_header:
            headers["Date"] = date_header
        resp.headers = headers
        return resp

    def _make_client(self):
        return CfKvClient(
            account_id="acct",
            namespace_id="ns",
            api_token="token",
            key="key",
        )

    @patch("cf_kv_client.requests")
    def test_basic_fetch(self, mock_requests):
        kv_data = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 22,
                "roomOffsets": {"LDK": 0},
                "updatedAt": "2026-02-25T11:04:41.596Z",
            }
        }
        mock_requests.get.return_value = self._mock_response(
            kv_data, date_header="Thu, 27 Feb 2026 12:00:00 GMT"
        )

        client = self._make_client()
        result = client.fetch_config()

        assert isinstance(result, KvResult)
        assert result.config.mode == "auto-steady"
        assert result.config.base_temp == 22
        assert result.updated_at == 1772103881
        assert result.process_time == 1772280000
        assert result.raw_data == kv_data

    @patch("cf_kv_client.requests")
    def test_auth_header_sent(self, mock_requests):
        kv_data = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 20,
                "roomOffsets": {},
            }
        }
        mock_requests.get.return_value = self._mock_response(kv_data)

        client = CfKvClient(
            account_id="acct",
            namespace_id="ns",
            api_token="my-secret-token",
            key="k",
        )
        client.fetch_config()

        call_kwargs = mock_requests.get.call_args
        headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs[1].get("headers")
        assert headers["Authorization"] == "Bearer my-secret-token"

    @patch("cf_kv_client.requests")
    def test_response_close_called(self, mock_requests):
        kv_data = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 20,
                "roomOffsets": {},
            }
        }
        resp = self._mock_response(kv_data)
        mock_requests.get.return_value = resp

        client = self._make_client()
        client.fetch_config()
        resp.close.assert_called_once()

    def test_missing_account_id_raises(self):
        with pytest.raises(ValueError):
            CfKvClient(
                account_id="", namespace_id="ns",
                api_token="tok", key="k",
            )

    def test_missing_api_token_raises(self):
        with pytest.raises(ValueError):
            CfKvClient(
                account_id="acct", namespace_id="ns",
                api_token="", key="k",
            )


# ---------------------------------------------------------------------------
# CfKvClient.update_current_settings (mocked HTTP)
# ---------------------------------------------------------------------------

class TestUpdateCurrentSettings:
    """Test CfKvClient.update_current_settings with mocked urequests."""

    def _mock_response(self, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.raise_for_status = MagicMock()
        resp.close = MagicMock()
        return resp

    def _make_client(self):
        return CfKvClient(
            account_id="acct",
            namespace_id="ns",
            api_token="tok",
            key="k",
        )

    @patch("cf_kv_client.requests")
    def test_basic_update(self, mock_requests):
        mock_requests.put.return_value = self._mock_response()

        raw_data = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 22,
                "roomOffsets": {"Room1": 0},
            }
        }
        current_state = {
            "mode": "auto-save",
            "base_temp": 24,
            "room_names": ["Room1"],
            "room_adjust": [3],
        }

        client = self._make_client()
        client.update_current_settings(
            raw_data=raw_data,
            current_state=current_state,
        )

        mock_requests.put.assert_called_once()
        call_kwargs = mock_requests.put.call_args[1]
        assert call_kwargs["headers"]["Content-Type"] == "application/json"
        # Verify body contains updated mode
        body = call_kwargs["data"]
        parsed = json.loads(body)
        assert parsed["currentSettings"]["mode"] == "auto-save"
        assert parsed["currentSettings"]["baseTemperature"] == 24

    @patch("cf_kv_client.requests")
    def test_mode_only_update(self, mock_requests):
        mock_requests.put.return_value = self._mock_response()

        raw_data = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 22,
                "roomOffsets": {"Room1": 0},
            }
        }
        current_state = {"mode": "-"}

        client = self._make_client()
        client.update_current_settings(
            raw_data=raw_data,
            current_state=current_state,
            mode_only=True,
        )

        body = mock_requests.put.call_args[1]["data"]
        parsed = json.loads(body)
        # Mode updated, temps preserved
        assert parsed["currentSettings"]["mode"] == "-"
        assert parsed["currentSettings"]["baseTemperature"] == 22
        assert parsed["currentSettings"]["roomOffsets"] == {"Room1": 0}

    @patch("cf_kv_client.requests")
    def test_response_close_called(self, mock_requests):
        resp = self._mock_response()
        mock_requests.put.return_value = resp

        raw_data = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 20,
                "roomOffsets": {},
            }
        }
        client = self._make_client()
        client.update_current_settings(
            raw_data=raw_data,
            current_state={
                "mode": "auto-steady", "base_temp": 20,
                "room_names": [], "room_adjust": [],
            },
        )
        resp.close.assert_called_once()

    @patch("cf_kv_client.requests")
    def test_multibyte_content_length(self, mock_requests):
        """Content-Length must be byte length, not character length."""
        mock_requests.put.return_value = self._mock_response()

        raw_data = {
            "currentSettings": {
                "mode": "auto-steady",
                "baseTemperature": 20,
                "roomOffsets": {"リビング": 0},  # multi-byte chars
            }
        }
        client = self._make_client()
        client.update_current_settings(
            raw_data=raw_data,
            current_state={
                "mode": "auto-steady", "base_temp": 20,
                "room_names": ["リビング"], "room_adjust": [2],
            },
        )

        call_kwargs = mock_requests.put.call_args[1]
        content_length = int(call_kwargs["headers"]["Content-Length"])
        body_bytes = call_kwargs["data"]
        assert content_length == len(body_bytes)
