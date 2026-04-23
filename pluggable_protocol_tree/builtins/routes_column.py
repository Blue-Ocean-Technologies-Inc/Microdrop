"""Routes column + RoutesHandler.

Per-step list of routes (each route = ordered list of electrode IDs).
Cell shows a read-only summary; the demo's SimpleDeviceViewer is the
primary edit path in PPT-3.

The RoutesHandler walks iter_phases() over the row's electrodes /
routes / trail config, publishes each phase to ELECTRODES_STATE_CHANGE
(JSON envelope with both electrode IDs and resolved channel numbers),
then blocks via ctx.wait_for() for the device's
ELECTRODES_STATE_APPLIED ack before requesting the next phase.

Priority 30 keeps this in a strictly earlier bucket than
DurationColumnHandler (90), so the duration sleep only starts after
ALL phases have completed and been ack'd.
"""

import json
import logging
import time

from pyface.qt.QtCore import Qt
from traits.api import List, Str

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.services.phase_math import iter_phases
from pluggable_protocol_tree.views.columns.base import BaseColumnView


logger = logging.getLogger(__name__)

# Sentinel set on ctx.scratch by RoutesHandler so DurationColumnHandler
# (priority 90) knows the per-phase dwells have already covered the
# row's total duration and shouldn't be slept again.
DURATION_CONSUMED_KEY = "_routes_consumed_duration"

# Cooperative-sleep slice: how often to check stop_event during a
# per-phase dwell so a Stop press lands within ~50ms even on long
# durations.
_SLICE_S = 0.05


class RoutesColumnModel(BaseColumnModel):
    """List[List[str]] trait. Default = empty list."""
    def trait_for_row(self):
        return List(List(Str), value=list(self.default_value or []),
                    desc="Per-step list of routes; each route is an "
                         "ordered list of electrode IDs.")


class RoutesSummaryView(BaseColumnView):
    """Read-only cell. '0 routes' / '1 route' / 'N routes'."""

    def format_display(self, value, row):
        n = len(value or [])
        return f"{n} route" + ("" if n == 1 else "s")

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def create_editor(self, parent, context):
        return None


class RoutesHandler(BaseColumnHandler):
    """Drives electrode actuation for the step. See module docstring.

    The row's ``duration_s`` is the dwell time PER PHASE. Each phase
    actuates for ``duration_s`` seconds before transitioning to the
    next; this matches the legacy protocol_grid where each protocol
    row was a single phase. After the last phase, RoutesHandler marks
    the per-step duration as consumed via ``ctx.scratch`` so the
    DurationColumnHandler at priority 90 doesn't dwell a second time.
    """
    priority = 30
    wait_for_topics = [ELECTRODES_STATE_APPLIED]

    def on_step(self, row, ctx):
        mapping = ctx.protocol.scratch.get("electrode_to_channel", {})
        per_phase_dwell = float(getattr(row, "duration_s", 0.0) or 0.0)
        stop_event = ctx.protocol.stop_event
        for phase in iter_phases(
            static_electrodes=list(getattr(row, "electrodes", []) or []),
            routes=list(getattr(row, "routes", []) or []),
            trail_length=int(getattr(row, "trail_length", 1)),
            trail_overlay=int(getattr(row, "trail_overlay", 0)),
            soft_start=bool(getattr(row, "soft_start", False)),
            soft_end=bool(getattr(row, "soft_end", False)),
            repeat_duration_s=float(getattr(row, "repeat_duration", 0.0)),
            linear_repeats=bool(getattr(row, "linear_repeats", False)),
            n_repeats=int(getattr(row, "repetitions", 1)),
            step_duration_s=float(getattr(row, "duration_s", 1.0)),
        ):
            if stop_event.is_set():
                break
            electrodes = sorted(phase)
            channels = sorted(mapping[e] for e in electrodes if e in mapping)
            for e in electrodes:
                if e not in mapping:
                    logger.warning(
                        "electrode %r has no channel mapping; "
                        "actuation channel skipped", e,
                    )
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps({
                    "electrodes": electrodes,
                    "channels": channels,
                }),
            )
            # 5.0s matches ack_roundtrip_column. Keeps headroom for the
            # first publish in a process (cold broker pays ~1-2s) and
            # for queue contention when other handlers in the same
            # priority bucket publish in parallel and serialize through
            # the single dramatiq worker queue. Hardware controllers
            # typically ack in <100ms.
            ctx.wait_for(ELECTRODES_STATE_APPLIED, timeout=5.0)
            _cooperative_sleep(per_phase_dwell, stop_event)
        # Tell DurationColumnHandler we already covered the dwell.
        ctx.scratch[DURATION_CONSUMED_KEY] = True


def _cooperative_sleep(seconds: float, stop_event) -> None:
    """Sleep for ``seconds``, waking every _SLICE_S to check stop_event.
    Used so a Stop press lands within ~50ms even mid-dwell. Returns
    early on stop or when seconds reaches 0."""
    remaining = seconds
    while remaining > 0:
        if stop_event.is_set():
            return
        slice_dur = min(_SLICE_S, remaining)
        time.sleep(slice_dur)
        remaining -= slice_dur


def make_routes_column():
    return Column(
        model=RoutesColumnModel(
            col_id="routes", col_name="Routes", default_value=[],
        ),
        view=RoutesSummaryView(),
        handler=RoutesHandler(),
    )
