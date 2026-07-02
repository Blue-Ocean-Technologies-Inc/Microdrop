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


def reconcile_readouts(existing, names, factory):
    """Return the readout list for ``names``, reusing existing instances by name
    (so their last values survive) and building missing ones via ``factory(name)``.
    Readouts for vanished heaters are dropped."""
    by_name = {r.name: r for r in existing}
    return [by_name.get(name) or factory(name) for name in names]


def heater_from_frame(frame):
    """The heater a ``PID_<HEATER>`` telemetry frame belongs to (e.g.
    ``PID_HEATER1`` -> ``heater1``), or None for frames that aren't per-heater."""
    if frame.startswith("PID_"):
        return frame[len("PID_"):].lower()
    return None


def telemetry_samples(data):
    """Extract the numeric plot samples from a telemetry frame.

    The status readouts use :func:`format_telemetry` (display strings); the
    plots need the raw numbers, so this is its numeric sibling and shares the
    same frame semantics. Returns a dict shaped as one of:

      * ``{"temperatures": {sensor_name: float}}``  — a ``TEMP`` frame's
        per-sensor snapshot,
      * ``{"heater": str, "pid_temperature": float?, "pwm_percentage": float?}``
        — a ``PID_<HEATER>`` frame (each numeric key present only when valid).

    Empty dict for frames with nothing plottable (WHOAMI / ERR / INFO / no
    valid readings). Sub-threshold temperature sentinels are dropped, matching
    the readout formatter.
    """
    frame = data.get("_frame", "")
    if frame in ("WHOAMI", "ERR", "INFO"):
        return {}

    heater = heater_from_frame(frame)
    if heater is not None:
        out = {"heater": heater}
        pid_temp = data.get("pid_temperature")
        if isinstance(pid_temp, (int, float)) and pid_temp > INVALID_TEMP_THRESHOLD:
            out["pid_temperature"] = float(pid_temp)
        pwm = data.get("pwm_percentage")
        if isinstance(pwm, (int, float)):
            out["pwm_percentage"] = float(pwm)
        return out

    temps = data.get("temperatures") or {}
    if isinstance(temps, dict):
        clean = {name: float(value) for name, value in temps.items()
                 if isinstance(value, (int, float)) and value > INVALID_TEMP_THRESHOLD}
        if clean:
            return {"temperatures": clean}
    return {}


def format_telemetry(data, pid_mode=False):
    """Map a telemetry frame to ``(heater, updates)``.

    ``heater`` is the channel name the per-heater ``updates`` (temperature_display
    / pwm_display) belong to, or None when the updates are global (board_id_text,
    all_temps_display). ERR/INFO frames are handled elsewhere (halt / logging).

    The board streams two frame kinds at once regardless of mode: ``TEMP`` frames
    carry only the per-sensor ``temperatures`` dict (global snapshot), and
    ``PID_<HEATER>`` frames carry that heater's ``pid_temperature`` plus
    ``pwm_percentage`` (the PID loop's duty, which is 0 whenever PID is disabled).
    The open-loop duty the user commands is *not* echoed anywhere, so the PWM
    readout is only driven from telemetry in closed-loop (``pid_mode``); in
    open-loop the controller echoes the commanded value instead.
    """
    frame = data.get("_frame", "")

    if frame == "WHOAMI":
        ident = data.get("device_id") or data.get("uid") or "unknown"
        return None, {"board_id_text": str(ident)}
    if frame in ("ERR", "INFO"):
        return None, {}

    heater = heater_from_frame(frame)
    if heater is not None:
        updates = {}
        pid_temp = data.get("pid_temperature")
        if isinstance(pid_temp, (int, float)):
            # Show the reading when valid, else reset to placeholder (the board
            # sends a sub-threshold sentinel when there's no PID reading).
            updates["temperature_display"] = (
                f"{pid_temp:.1f} °C" if pid_temp > INVALID_TEMP_THRESHOLD else "-"
            )
        if pid_mode:
            pwm = data.get("pwm_percentage")
            if isinstance(pwm, (int, float)):
                updates["pwm_display"] = f"{pwm} %"
        return heater, updates

    # TEMP (and any other non-per-heater frame): the all-sensor snapshot.
    temps = data.get("temperatures") or {}
    if isinstance(temps, dict):
        parts = [
            f"{name}: {value:.1f} °C"
            for name, value in temps.items()
            if isinstance(value, (int, float))
        ]
        if parts:
            return None, {"all_temps_display": ", ".join(parts)}

    return None, {}
