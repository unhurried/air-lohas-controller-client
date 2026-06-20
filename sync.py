"""Sync loop logic: aircon <-> Cloudflare KV synchronisation."""


MODE_POWER_OFF = "-"


def is_power_off(mode):
    """Return True if *mode* represents power-off."""
    return mode == MODE_POWER_OFF


# ---------------------------------------------------------------------------
# Settings comparison
# ---------------------------------------------------------------------------

def settings_differ(current, config):
    """Check if aircon current state differs from KV config.

    When the aircon is powered off, only mode is compared;
    base_temp and room offsets are ignored.
    Fields where the aircon returns None are skipped.
    """
    if current["mode"] is not None and current["mode"] != config.mode:
        return True

    if is_power_off(current["mode"]):
        return False

    if current["base_temp"] is not None and current["base_temp"] != config.base_temp:
        return True

    room_names = current["room_names"]
    room_adjust = current["room_adjust"]
    name_index = {name: idx for idx, name in enumerate(room_names) if name}

    for room_name, desired in config.rooms.items():
        idx = name_index.get(room_name)
        if idx is None or idx >= len(room_adjust):
            continue
        if room_adjust[idx] != desired:
            return True

    return False


def settings_from_aircon(current):
    """Build normalised settings dict from aircon state."""
    room_names = current["room_names"]
    room_adjust = current["room_adjust"]
    rooms = {}
    for i, name in enumerate(room_names):
        if not name or i >= len(room_adjust):
            continue
        rooms[name] = room_adjust[i]
    return {
        "mode": current["mode"],
        "base_temp": current["base_temp"],
        "rooms": rooms,
    }


def settings_from_config(config):
    """Build normalised settings dict from Config object."""
    return {
        "mode": config.mode,
        "base_temp": config.base_temp,
        "rooms": dict(config.rooms),
    }


# ---------------------------------------------------------------------------
# Room offset helpers
# ---------------------------------------------------------------------------

def find_changed_rooms(room_names, room_adjust, desired_rooms):
    """Return list of room names whose adjust value differs from desired."""
    name_index = {name: idx for idx, name in enumerate(room_names) if name}
    changed = []

    for room_name, desired_value in desired_rooms.items():
        idx = name_index.get(room_name)
        if idx is None or idx >= len(room_adjust):
            changed.append(room_name)
            continue
        if room_adjust[idx] != desired_value:
            changed.append(room_name)

    return changed


def build_adjust_from_current(current, updates):
    """Build a full adjust array by merging *updates* into *current* state."""
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


# ---------------------------------------------------------------------------
# Apply KV -> Aircon
# ---------------------------------------------------------------------------

def _apply_power_off(power_client, current_mode):
    """Turn off aircon power.  Skips if already off or mode unknown."""
    if current_mode is None:
        print("power off skipped: current mode unknown")
        return
    if is_power_off(current_mode):
        print("power already off")
        return
    power_client.power_off()
    print("power off executed")


def _apply_power_on_and_settings(client, power_client, current, config):
    """Turn on aircon power then unconditionally apply all KV settings."""
    power_client.power_on()
    print("power on executed")

    target_mode = config.mode
    if target_mode == "auto-steady":
        client.set_auto_steady()
        print("mode set -> auto-steady")
    elif target_mode == "auto-save":
        client.set_auto_save()
        print("mode set -> auto-save")

    client.set_base_temp(config.base_temp)
    print(f"base temp set -> {config.base_temp}")

    if config.rooms:
        new_adjust = build_adjust_from_current(current, config.rooms)
        client.set_room_adjust(new_adjust)
        print("room offsets set")


def _apply_mode_and_temps(client, current, config):
    """Apply mode / base-temp / room-offset changes (both sides powered on)."""
    current_mode = current["mode"]
    current_base_temp = current["base_temp"]
    target_mode = config.mode

    # Mode -----------------------------------------------------------------
    if current_mode is None:
        print("mode unchanged (current mode unknown, skipped)")
    elif current_mode != target_mode:
        if target_mode == "auto-steady":
            client.set_auto_steady()
            print("mode changed -> auto-steady")
        elif target_mode == "auto-save":
            client.set_auto_save()
            print("mode changed -> auto-save")
    else:
        print("mode unchanged")

    # Base temperature -----------------------------------------------------
    if current_base_temp is None:
        print("base temp unchanged (current temp unknown, skipped)")
    elif current_base_temp != config.base_temp:
        client.set_base_temp(config.base_temp)
        print(f"base temp changed -> {config.base_temp}")
    else:
        print("base temp unchanged")

    # Room offsets ---------------------------------------------------------
    if config.rooms:
        changed_rooms = find_changed_rooms(
            current["room_names"],
            current["room_adjust"],
            config.rooms,
        )
        if changed_rooms:
            print("changed rooms: " + ", ".join(changed_rooms))
            new_adjust = build_adjust_from_current(current, config.rooms)
            client.set_room_adjust(new_adjust)
            print("room offsets changed")
        else:
            print("room offsets unchanged")


def apply_kv_to_aircon(client, power_client, current, config):
    """Apply KV config to aircon (power, mode, base_temp, room offsets).

    * Power off  -> just turn off; skip base_temp / rooms.
    * Power on   -> turn on first, then set mode + base_temp + rooms.
    * Otherwise  -> normal mode / temp / room update.
    """
    current_mode = current["mode"]
    target_mode = config.mode

    if is_power_off(target_mode):
        _apply_power_off(power_client, current_mode)
        return

    if current_mode is not None and is_power_off(current_mode):
        _apply_power_on_and_settings(client, power_client, current, config)
        return

    _apply_mode_and_temps(client, current, config)


# ---------------------------------------------------------------------------
# Update Aircon -> KV
# ---------------------------------------------------------------------------

def _update_kv_from_aircon(kv_result, current, kv_client):
    """Write current aircon state back to KV.

    When the aircon is powered off, only mode is written;
    base_temp and room offsets in KV are preserved.
    """
    current_mode = current["mode"]

    if current_mode is None:
        print("KV update skipped: aircon mode unknown")
        return

    if is_power_off(current_mode):
        kv_client.update_current_settings(
            raw_data=kv_result.raw_data,
            current_state=current,
            mode_only=True,
        )
        print("KV updated with power-off mode (temps preserved)")
        return

    if current["base_temp"] is None:
        print("KV update skipped: aircon base temp unknown")
        return

    kv_client.update_current_settings(
        raw_data=kv_result.raw_data,
        current_state=current,
    )
    print("KV updated with aircon settings")


# ---------------------------------------------------------------------------
# Single sync iteration
# ---------------------------------------------------------------------------

def run_once(state, client, power_client, kv_client):
    """Execute one sync iteration."""
    current = client.get_current_state()
    print(
        f"aircon state: mode={current['mode']}"
        f" base_temp={current['base_temp']}"
    )

    kv_result = kv_client.fetch_config()
    process_time = kv_result.process_time
    config = kv_result.config
    print(f"KV config: mode={config.mode} base_temp={config.base_temp}")

    if settings_differ(current, config):
        if kv_result.updated_at > state.last_process_time:
            print(
                f"settings differ: KV is newer "
                f"(updatedAt={kv_result.updated_at} > "
                f"last_process_time={state.last_process_time})"
            )
            apply_kv_to_aircon(client, power_client, current, config)
            recorded = settings_from_config(config)
        else:
            print(
                f"settings differ: aircon is newer "
                f"(updatedAt={kv_result.updated_at} <= "
                f"last_process_time={state.last_process_time})"
            )
            _update_kv_from_aircon(kv_result, current, kv_client)
            recorded = settings_from_aircon(current)
    else:
        print("settings unchanged")
        recorded = settings_from_aircon(current)

    state.update(process_time, recorded)
    print(f"sync done (process_time={process_time})")
