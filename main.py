from ac_http_client import AcHttpClient
from ac_echonet_client import AcEchonetClient
from cf_kv_client import CfKvClient
from state import LoopState
from sync import run_once
from settings import (
    INTERVAL_SECONDS,
    WIFI_SSID,
    WIFI_PASSWORD,
    BASE_URL,
    ROOM_ID,
    ROOM_INFO_ID,
    CF_ACCOUNT_ID,
    CF_KV_NAMESPACE_ID,
    CF_API_TOKEN,
    CF_KV_KEY,
    AIRCON_IP,
    AIRCON_EOJ,
)

import machine
from machine import WDT
import network
import utime

WDT_MAX_TIMEOUT_MS = 8000
WDT_MIN_TIMEOUT_MS = 1000
RESET_ON_CONSECUTIVE_ERRORS = 3


def _feed_watchdog(wdt):
    if wdt is not None:
        wdt.feed()


def _connect_wifi(timeout_sec=20, wdt=None):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return wlan.ifconfig()

    wlan.connect(WIFI_SSID, WIFI_PASSWORD, security=wlan.SEC_WPA3)

    start = utime.ticks_ms()
    timeout_ms = timeout_sec * 1000

    while not wlan.isconnected():
        if utime.ticks_diff(utime.ticks_ms(), start) > timeout_ms:
            raise RuntimeError("Wi-Fi connection timed out")
        _feed_watchdog(wdt)
        utime.sleep_ms(200)

    return wlan.ifconfig()


def _wdt_timeout_ms(interval_seconds):
    return min(
        WDT_MAX_TIMEOUT_MS,
        max(WDT_MIN_TIMEOUT_MS, int(interval_seconds * 2 * 1000)),
    )


def _request_timeout_seconds(wdt_timeout_ms):
    return max(1, (wdt_timeout_ms - 1000) // 1000)


def _sleep_with_wdt(interval_seconds, wdt, wdt_timeout_ms):
    remaining_ms = max(0, int(interval_seconds * 1000))
    chunk_ms = max(1, wdt_timeout_ms // 2)

    while remaining_ms > 0:
        sleep_ms = min(remaining_ms, chunk_ms)
        _feed_watchdog(wdt)
        utime.sleep_ms(sleep_ms)
        remaining_ms -= sleep_ms


def main():
    if WIFI_SSID == "YOUR_SSID":
        raise ValueError("Set WIFI_SSID / WIFI_PASSWORD before running")
    if BASE_URL == "http://YOUR_BASE_URL":
        raise ValueError("Set BASE_URL / ROOM_ID / ROOM_INFO_ID before running")
    if (
        CF_ACCOUNT_ID == "YOUR_CLOUDFLARE_ACCOUNT_ID"
        or CF_KV_NAMESPACE_ID == "YOUR_KV_NAMESPACE_ID"
        or CF_API_TOKEN == "YOUR_CLOUDFLARE_API_TOKEN"
    ):
        raise ValueError(
            "Set CF_ACCOUNT_ID / CF_KV_NAMESPACE_ID / CF_API_TOKEN before running"
        )
    if AIRCON_IP == "YOUR_AIRCON_IP":
        raise ValueError("Set AIRCON_IP before running")

    wdt_timeout_ms = _wdt_timeout_ms(INTERVAL_SECONDS)
    request_timeout_seconds = _request_timeout_seconds(wdt_timeout_ms)

    client = AcHttpClient(
        base_url=BASE_URL,
        room_id=ROOM_ID,
        room_info_id=ROOM_INFO_ID,
        timeout=request_timeout_seconds,
    )

    power_client = AcEchonetClient(
        aircon_ip=AIRCON_IP,
        eoj=AIRCON_EOJ,
        timeout=request_timeout_seconds,
    )

    kv_client = CfKvClient(
        account_id=CF_ACCOUNT_ID,
        namespace_id=CF_KV_NAMESPACE_ID,
        api_token=CF_API_TOKEN,
        key=CF_KV_KEY,
        timeout=request_timeout_seconds,
    )

    state = LoopState()
    wdt = WDT(timeout=wdt_timeout_ms)
    consecutive_errors = 0

    print(
        "start sync-loop: source=Cloudflare Workers KV, "
        f"key={CF_KV_KEY}, interval={INTERVAL_SECONDS}s, "
        f"wdt_timeout={wdt_timeout_ms}ms, "
        f"request_timeout={request_timeout_seconds}s"
    )
    while True:
        try:
            ifconfig = _connect_wifi(wdt=wdt)
            print("Wi-Fi connected:", ifconfig)
            run_once(state, client, power_client, kv_client, feed_wdt=wdt.feed)
            consecutive_errors = 0
        except Exception as exc:
            consecutive_errors += 1
            print(f"sync error: {exc}")
            print(
                f"consecutive errors: {consecutive_errors}/"
                f"{RESET_ON_CONSECUTIVE_ERRORS}"
            )
            if consecutive_errors >= RESET_ON_CONSECUTIVE_ERRORS:
                print("too many consecutive errors, executing soft reset")
                machine.reset()

        print(f"sleep {INTERVAL_SECONDS}s")
        _sleep_with_wdt(INTERVAL_SECONDS, wdt, wdt_timeout_ms)


if __name__ == "__main__":
    main()
