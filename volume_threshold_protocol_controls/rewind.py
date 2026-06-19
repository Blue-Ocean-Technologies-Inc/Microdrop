"""Pure helpers for the volume-threshold "Rewind" action.

Rewind runs a droplet check across the step's route channels, infers which
phase the droplet is currently sitting at, and seeks execution back to that
phase. These functions are Qt-free, IO-free, and thread-free so they unit-test
without the executor or a DropBot:

  * ``step_route_phases`` rebuilds the step's phase list (one pass, static mode)
    the same way RoutesHandler does.
  * ``route_channels`` lists the channels the droplet check should sample.
  * ``rewind_target_phase`` maps the detected channels back to a single phase
    index (the droplet's leading-edge phase), or None when the result is
    absent / off-route / ambiguous.
"""

from typing import List, Optional, Set

from pluggable_protocol_tree.services.phase_math import iter_phases


def step_route_phases(row) -> List[Set[str]]:
    """Ordered electrode-id sets for ONE pass of the step's routes.

    Mirrors RoutesHandler's static-mode ``iter_phases`` call (Rewind is scoped
    to non-duration steps, so ``repeat_duration_s=0``)."""
    return list(iter_phases(
        static_electrodes=list(getattr(row, "electrodes", []) or []),
        routes=list(getattr(row, "routes", []) or []),
        trail_length=int(getattr(row, "trail_length", 1)),
        trail_overlay=int(getattr(row, "trail_overlay", 0)),
        soft_start=bool(getattr(row, "soft_start", False)),
        soft_end=bool(getattr(row, "soft_end", False)),
        repeat_duration_s=0.0,
        linear_repeats=bool(getattr(row, "linear_repeats", False)),
        n_repeats=int(getattr(row, "route_repetitions", 1)),
        step_duration_s=float(getattr(row, "duration_s", 1.0)),
    ))


def route_channels(row, electrode_to_channel) -> List[int]:
    """Sorted unique channels touched by the step's routes -- the set the
    droplet check actuates to find where the droplet is. Electrode IDs with no
    channel mapping are dropped."""
    chans = set()
    for route in (getattr(row, "routes", []) or []):
        for eid in route:
            ch = electrode_to_channel.get(eid)
            if ch is not None:
                chans.add(int(ch))
    return sorted(chans)


def rewind_target_phase(phases, electrode_to_channel,
                        detected_channels) -> Optional[int]:
    """Phase index to rewind to, or None.

    ``phases`` is the ordered list of electrode-id sets (``step_route_phases``).
    Each detected channel is translated back to the route and resolved to the
    phase where it FIRST appears -- its leading-edge phase (for ``trail_length``
    1 this is just the phase that actuates it). Returns that index only when all
    on-route detected channels resolve to a SINGLE phase; returns None when no
    detected channel lies on the route, or they map to more than one phase
    (ambiguous -- the caller shows a notice and does not rewind)."""
    detected = {int(c) for c in detected_channels}
    if not detected:
        return None
    chan_phases = [
        {int(electrode_to_channel[e]) for e in ph if e in electrode_to_channel}
        for ph in phases
    ]
    targets = set()
    for channel in detected:
        if not any(channel in cp for cp in chan_phases):
            continue  # not on this route -> ignore
        for index, cp in enumerate(chan_phases):
            if channel in cp and (index == 0 or channel not in chan_phases[index - 1]):
                targets.add(index)
                break
    if len(targets) != 1:
        return None
    return next(iter(targets))
