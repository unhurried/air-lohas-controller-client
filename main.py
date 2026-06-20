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

import network
import utime


def _connect_wifi(timeout_sec=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return wlan.ifconfig()

    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    start = utime.ticks_ms()
    timeout_ms = timeout_sec * 1000

    while not wlan.isconnected():
        if utime.ticks_diff(utime.ticks_ms(), start) > timeout_ms:
            raise RuntimeError("Wi-Fi connection timed out")
        utime.sleep_ms(200)

    return wlan.ifconfig()


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

    ifconfig = _connect_wifi()
    print("Wi-Fi connected:", ifconfig)

    client = AcHttpClient(
        base_url=BASE_URL,
        room_id=ROOM_ID,
        room_info_id=ROOM_INFO_ID,
    )

    power_client = AcEchonetClient(
        aircon_ip=AIRCON_IP,
        eoj=AIRCON_EOJ,
    )

    kv_client = CfKvClient(
        account_id=CF_ACCOUNT_ID,
        namespace_id=CF_KV_NAMESPACE_ID,
        api_token=CF_API_TOKEN,
        key=CF_KV_KEY,
    )

    state = LoopState()

    print(
        "start sync-loop: source=Cloudflare Workers KV, "
        f"key={CF_KV_KEY}, interval={INTERVAL_SECONDS}s"
    )
    while True:
        started_ms = utime.ticks_ms()
        try:
            run_once(state, client, power_client, kv_client)
        except Exception as exc:
            print(f"sync error: {exc}")

        elapsed_ms = utime.ticks_diff(utime.ticks_ms(), started_ms)
        sleep_ms = (INTERVAL_SECONDS * 1000) - elapsed_ms
        if sleep_ms < 0:
            sleep_ms = 0
        print(f"sleep {int(sleep_ms / 1000)}s")
        utime.sleep_ms(int(sleep_ms))


if __name__ == "__main__":
    main()
