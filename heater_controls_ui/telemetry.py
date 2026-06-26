"""Pure helpers that turn heater backend signals into model updates.

No Qt / traits / dramatiq here, so these are straightforward to unit-test.
"""

INVALID_TEMP_THRESHOLD = -40  # telemetry sends sentinels below this when no reading


def resolve_selection(current, heaters):
    """Return the ``selected_heater`` update needed so the selection always points
    at a real channel: default to the first when unset or no longer present."""
    if heaters and current not in heaters:
        return {"selected_heater": heaters[0]}
    return {}


def format_telemetry(data):
    """Map a telemetry dict to the model display-field updates it should drive.

    Returns only the fields the frame carries, so unrelated readouts keep their
    last value. ERR/INFO frames are handled elsewhere (halt state / logging).
    """
    frame = data.get("_frame", "")

    if frame == "WHOAMI":
        ident = data.get("device_id") or data.get("uid") or "unknown"
        return {"board_id_text": str(ident)}
    if frame in ("ERR", "INFO"):
        return {}

    # TEMP / PID_<HEATER> telemetry
    updates = {}
    pid_temp = data.get("pid_temperature")
    if isinstance(pid_temp, (int, float)) and pid_temp > INVALID_TEMP_THRESHOLD:
        updates["temperature_display"] = f"{pid_temp:.1f} °C"

    pwm = data.get("pwm_percentage", data.get("pwm_tec1"))
    if isinstance(pwm, (int, float)):
        updates["pwm_display"] = f"{pwm} %"

    temps = data.get("temperatures") or {}
    if isinstance(temps, dict):
        parts = [
            f"{name}: {value:.1f} °C"
            for name, value in temps.items()
            if isinstance(value, (int, float))
        ]
        if parts:
            updates["all_temps_display"] = ", ".join(parts)

    return updates
