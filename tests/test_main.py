"""Tests for the main sync loop."""

from unittest.mock import MagicMock, call

import pytest

import main


class StopLoop(Exception):
    """Raised by tests to stop the infinite loop in main()."""


def _configure_runtime_settings(monkeypatch):
    monkeypatch.setattr(main, "WIFI_SSID", "ssid")
    monkeypatch.setattr(main, "WIFI_PASSWORD", "password")
    monkeypatch.setattr(main, "BASE_URL", "http://example.com")
    monkeypatch.setattr(main, "ROOM_ID", 1)
    monkeypatch.setattr(main, "ROOM_INFO_ID", 2)
    monkeypatch.setattr(main, "CF_ACCOUNT_ID", "account")
    monkeypatch.setattr(main, "CF_KV_NAMESPACE_ID", "namespace")
    monkeypatch.setattr(main, "CF_API_TOKEN", "token")
    monkeypatch.setattr(main, "CF_KV_KEY", "aircon-settings-v1")
    monkeypatch.setattr(main, "AIRCON_IP", "192.0.2.10")
    monkeypatch.setattr(main, "AIRCON_EOJ", "0x013001")
    monkeypatch.setattr(main, "INTERVAL_SECONDS", 75)


def _configure_runtime_deps(monkeypatch):
    monkeypatch.setattr(main, "AcHttpClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(main, "AcEchonetClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(main, "CfKvClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(main, "LoopState", MagicMock(return_value=MagicMock()))


def test_main_retries_wifi_on_next_loop(monkeypatch):
    _configure_runtime_settings(monkeypatch)
    _configure_runtime_deps(monkeypatch)

    connect_wifi = MagicMock(side_effect=[RuntimeError("wifi down"), "ifconfig"])
    run_once = MagicMock()
    sleep_with_wdt = MagicMock(side_effect=[None, StopLoop()])
    wdt = MagicMock()
    wdt_cls = MagicMock(return_value=wdt)

    monkeypatch.setattr(main, "_connect_wifi", connect_wifi)
    monkeypatch.setattr(main, "run_once", run_once)
    monkeypatch.setattr(main, "_sleep_with_wdt", sleep_with_wdt)
    monkeypatch.setattr(main, "WDT", wdt_cls)

    with pytest.raises(StopLoop):
        main.main()

    assert connect_wifi.call_count == 2
    run_once.assert_called_once()
    wdt_cls.assert_called_once_with(timeout=8000)
    assert wdt.feed.call_count == 0
    assert connect_wifi.call_args_list == [call(wdt=wdt), call(wdt=wdt)]
    run_once.assert_called_once_with(
        main.LoopState.return_value,
        main.AcHttpClient.return_value,
        main.AcEchonetClient.return_value,
        main.CfKvClient.return_value,
        feed_wdt=wdt.feed,
    )
    assert sleep_with_wdt.call_args_list == [call(75, wdt, 8000), call(75, wdt, 8000)]


def test_main_waits_fixed_interval_after_each_loop(monkeypatch):
    _configure_runtime_settings(monkeypatch)
    _configure_runtime_deps(monkeypatch)

    connect_wifi = MagicMock(return_value="ifconfig")
    run_once = MagicMock()
    sleep_with_wdt = MagicMock(side_effect=StopLoop())
    wdt = MagicMock()
    wdt_cls = MagicMock(return_value=wdt)

    monkeypatch.setattr(main, "_connect_wifi", connect_wifi)
    monkeypatch.setattr(main, "run_once", run_once)
    monkeypatch.setattr(main, "_sleep_with_wdt", sleep_with_wdt)
    monkeypatch.setattr(main, "WDT", wdt_cls)

    with pytest.raises(StopLoop):
        main.main()

    connect_wifi.assert_called_once_with(wdt=wdt)
    run_once.assert_called_once_with(
        main.LoopState.return_value,
        main.AcHttpClient.return_value,
        main.AcEchonetClient.return_value,
        main.CfKvClient.return_value,
        feed_wdt=wdt.feed,
    )
    wdt_cls.assert_called_once_with(timeout=8000)
    wdt.feed.assert_not_called()
    sleep_with_wdt.assert_called_once_with(75, wdt, 8000)


def test_wdt_timeout_scales_from_interval_seconds():
    assert main._wdt_timeout_ms(75) == 8000
    assert main._wdt_timeout_ms(3) == 6000
    assert main._wdt_timeout_ms(0) == 1000


def test_request_timeout_stays_within_wdt_window():
    assert main._request_timeout_seconds(8000) == 7
    assert main._request_timeout_seconds(6000) == 5
    assert main._request_timeout_seconds(1000) == 1


def test_sleep_with_wdt_feeds_watchdog_between_chunks(monkeypatch):
    sleep_ms = MagicMock()
    wdt = MagicMock()

    monkeypatch.setattr(main.utime, "sleep_ms", sleep_ms)

    main._sleep_with_wdt(9, wdt, 8000)

    assert sleep_ms.call_args_list == [call(4000), call(4000), call(1000)]
    assert wdt.feed.call_count == 3


def test_connect_wifi_feeds_watchdog_while_waiting(monkeypatch):
    wlan = MagicMock()
    wlan.isconnected.side_effect = [False, False, False, True]
    wlan.ifconfig.return_value = "ifconfig"
    wdt = MagicMock()

    monkeypatch.setattr(main, "WIFI_SSID", "ssid")
    monkeypatch.setattr(main, "WIFI_PASSWORD", "password")
    monkeypatch.setattr(main.network, "WLAN", MagicMock(return_value=wlan))
    monkeypatch.setattr(main.utime, "sleep_ms", MagicMock())

    assert main._connect_wifi(wdt=wdt) == "ifconfig"

    wlan.connect.assert_called_once_with(
        main.WIFI_SSID,
        main.WIFI_PASSWORD,
        security=wlan.SEC_WPA3,
    )
    assert wdt.feed.call_count == 2