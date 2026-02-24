from client import AirLohasClient
from config import load_config_from_cloudflare_kv
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


def _find_changed_rooms(room_names, room_adjust, desired_rooms):
    name_index = {name: idx for idx, name in enumerate(room_names) if name}
    changed = []

    for room_name, desired_value in desired_rooms.items():
        idx = name_index.get(room_name)
        if idx is None:
            changed.append(room_name)
            continue
        if idx >= len(room_adjust):
            changed.append(room_name)
            continue

        current_value = room_adjust[idx]
        if current_value != desired_value:
            changed.append(room_name)

    return changed


def _build_update_plan(current, settings):
    current_mode = current["mode"]
    current_base_temp = current["base_temp"]

    return {
        "current_mode": current_mode,
        "current_base_temp": current_base_temp,
        "mode_changed": current_mode != settings.mode,
        "base_temp_changed": current_base_temp != settings.base_temp,
        "changed_rooms": _find_changed_rooms(
            current["room_names"],
            current["room_adjust"],
            settings.rooms,
        ),
    }


def _build_adjust_from_current(current, updates):
    room_names = current["room_names"]
    room_adjust = current["room_adjust"]

    name_index = {name: idx for idx, name in enumerate(room_names) if name}
    adjusted = list(room_adjust)

    for room_name, value in updates.items():
        idx = name_index.get(room_name)
        if idx is None:
            raise ValueError(f"room name not found: {room_name}")
        if idx >= len(adjusted):
            raise ValueError(f"room index out of range for: {room_name}")
        adjusted[idx] = value

    return adjusted


def _apply_current_settings(client, settings):
    current = client.get_current_state()

    if current["mode"] == "stopped":
        print("update skipped: aircon is stopped (current_mode='-')")
        return

    plan = _build_update_plan(current, settings)
    current_mode = plan["current_mode"]
    current_base_temp = plan["current_base_temp"]

    mode_changed = plan["mode_changed"]
    base_temp_changed = plan["base_temp_changed"]
    changed_rooms = plan["changed_rooms"]

    summary = []
    if current_mode is None:
        summary.append("mode:unknown(skip)")
    if mode_changed:
        summary.append(f"mode:{current_mode}->{settings.mode}")
    if current_base_temp is None:
        summary.append("base_temp:unknown(skip)")
    if base_temp_changed:
        summary.append(
            f"base_temp:{current_base_temp}->{settings.base_temp}"
        )
    if changed_rooms:
        summary.append(f"room_offsets:{len(changed_rooms)} rooms")

    if summary:
        print("update plan: " + ", ".join(summary))
        if changed_rooms:
            print("update rooms: " + ", ".join(changed_rooms))
    else:
        print("update plan: no changes")

    if mode_changed:
        if settings.mode == "auto-steady":
            client.set_auto_steady()
            print("mode changed -> auto-steady")
        elif settings.mode == "auto-save":
            client.set_auto_save()
            print("mode changed -> auto-save")
    elif current_mode is None:
        print("mode unchanged (current mode unknown, skipped)")
    else:
        print("mode unchanged")

    if base_temp_changed:
        client.set_base_temp(settings.base_temp)
        print(f"base temp changed -> {settings.base_temp}")
    elif current_base_temp is None:
        print("base temp unchanged (current temp unknown, skipped)")
    else:
        print("base temp unchanged")

    if settings.rooms:
        if changed_rooms:
            new_adjust = _build_adjust_from_current(current, settings.rooms)
            client.set_room_adjust(new_adjust)
            print("room offsets changed")
        else:
            print("room offsets unchanged")


def _run_once():
    settings = load_config_from_cloudflare_kv(
        account_id=CF_ACCOUNT_ID,
        namespace_id=CF_KV_NAMESPACE_ID,
        api_token=CF_API_TOKEN,
        key=CF_KV_KEY,
    )
    client = AirLohasClient(
        base_url=BASE_URL,
        room_id=ROOM_ID,
        room_info_id=ROOM_INFO_ID,
    )
    _apply_current_settings(client, settings)
    print("currentSettings sync done")


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

    ifconfig = _connect_wifi()
    print("Wi-Fi connected:", ifconfig)

    print(
        "start apply-loop: source=Cloudflare Workers KV, "
        f"key={CF_KV_KEY}, interval={INTERVAL_SECONDS}s"
    )
    while True:
        started_ms = utime.ticks_ms()
        try:
            _run_once()
        except Exception as exc:
            print(f"apply error: {exc}")

        elapsed_ms = utime.ticks_diff(utime.ticks_ms(), started_ms)
        sleep_ms = (INTERVAL_SECONDS * 1000) - elapsed_ms
        if sleep_ms < 0:
            sleep_ms = 0
        print(f"sleep {int(sleep_ms / 1000)}s")
        utime.sleep_ms(int(sleep_ms))


if __name__ == "__main__":
    main()
