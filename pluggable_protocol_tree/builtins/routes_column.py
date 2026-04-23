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
    """Drives electrode actuation for the step. See module docstring."""
    priority = 30
    wait_for_topics = [ELECTRODES_STATE_APPLIED]

    def on_step(self, row, ctx):
        mapping = ctx.protocol.scratch.get("electrode_to_channel", {})
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
            ctx.wait_for(ELECTRODES_STATE_APPLIED, timeout=2.0)


def make_routes_column():
    return Column(
        model=RoutesColumnModel(
            col_id="routes", col_name="Routes", default_value=[],
        ),
        view=RoutesSummaryView(),
        handler=RoutesHandler(),
    )
