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


def format_telemetry(data, pid_mode=False):
    """Map a telemetry dict to the model display-field updates it should drive.

    Returns only the fields the frame carries, so unrelated readouts keep their
    last value. ERR/INFO frames are handled elsewhere (halt state / logging).

    The board streams two frame kinds at once regardless of mode: ``TEMP`` frames
    carry only the per-sensor ``temperatures`` dict, and ``PID_<HEATER>`` frames
    carry ``pid_temperature`` plus ``pwm_percentage`` (the PID loop's duty, which
    is 0 whenever PID is disabled). The open-loop duty the user commands is *not*
    echoed anywhere, so the main PWM readout is only driven from telemetry in
    closed-loop (``pid_mode``); in open-loop the controller echoes the commanded
    value instead. ``pid_mode`` says whether the UI's Temp mode is selected.
    """
    frame = data.get("_frame", "")

    if frame == "WHOAMI":
        ident = data.get("device_id") or data.get("uid") or "unknown"
        return {"board_id_text": str(ident)}
    if frame in ("ERR", "INFO"):
        return {}

    updates = {}
    pid_temp = data.get("pid_temperature")
    if isinstance(pid_temp, (int, float)):
        # Show the reading when valid, else reset to placeholder (the board sends
        # a sub-threshold sentinel when there's no PID reading).
        updates["temperature_display"] = (
            f"{pid_temp:.1f} °C" if pid_temp > INVALID_TEMP_THRESHOLD else "-"
        )

    # Only the closed-loop PID duty is reported; open-loop duty is echoed by the
    # controller from the commanded value (see HeaterControlsController).
    if pid_mode:
        pwm = data.get("pwm_percentage")
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
