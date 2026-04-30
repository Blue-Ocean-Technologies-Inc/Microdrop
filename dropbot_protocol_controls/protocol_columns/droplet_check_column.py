"""PPT-8: per-step droplet check column. After a step's phases complete,
the handler publishes DETECT_DROPLETS for the channels we expect droplets
on, awaits the backend's DROPLETS_DETECTED reply, and on missing channels
drives a UI confirm dialog via topic round-trip.

This file holds the pure helper, the model/view/factory, and the handler.
Splitting them across files would just spread cohesive logic; see PPT-7's
force_column.py for the same single-file convention.
"""

from logger.logger_service import get_logger

logger = get_logger(__name__)


def expected_channels_for_step(row, electrode_to_channel: dict) -> list:
    """Channels we expect droplets on after this step's phases finish.

    Mirrors legacy _get_expected_droplet_channels
    (protocol_runner_controller.py:1763): the union of
    (statically activated electrodes) and (the LAST electrode of each
    route — that's where the droplet ends up). Returns a sorted unique
    list of int channels. Unknown electrode IDs are silently dropped
    rather than raising — same behavior as legacy.
    """
    expected = set()
    for eid in (row.activated_electrodes or []):
        ch = electrode_to_channel.get(eid)
        if ch is not None:
            expected.add(int(ch))
    for route in (row.routes or []):
        if route:
            ch = electrode_to_channel.get(route[-1])
            if ch is not None:
                expected.add(int(ch))
    return sorted(expected)
