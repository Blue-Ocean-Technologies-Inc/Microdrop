"""Step duration in seconds.

Stored as a Float trait on each row. Not meaningful on groups; the
double-spinbox view already marks group cells non-editable.

The DurationColumnHandler sleeps for row.duration_s during on_step at
priority 90 — late enough that other on_step hooks (route actuation,
voltage application, etc.) have already published their commands and
this handler provides the dwell time during which the action takes
effect.
"""

import time

from traits.api import Float

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import DoubleSpinBoxColumnView


class DurationColumnModel(BaseColumnModel):
    def trait_for_row(self):
        # Honor the model's declared default_value rather than
        # hard-coding a literal — lets callers (e.g. fast unit-test
        # fixtures) configure the dwell-time default per protocol.
        return Float(float(self.default_value or 0.0),
                     desc="Dwell time for this step in seconds")


class DurationColumnHandler(BaseColumnHandler):
    """Sleeps for row.duration_s seconds in on_step.

    Sleep is cooperative: a 50ms slice loop checks ctx.protocol.stop_event
    every tick so a user Stop press lands within ~50ms even if the
    duration is long. Without this, a 30-second duration would block
    the worker thread for the full 30s past the Stop press.
    """
    priority = 90

    _SLICE_S = 0.05

    def on_step(self, row, ctx):
        remaining = float(getattr(row, "duration_s", 0.0) or 0.0)
        while remaining > 0:
            if ctx.protocol.stop_event.is_set():
                return
            sleep_for = min(self._SLICE_S, remaining)
            time.sleep(sleep_for)
            remaining -= sleep_for


def make_duration_column():
    return Column(
        model=DurationColumnModel(
            col_id="duration_s", col_name="Duration (s)", default_value=1.0,
        ),
        view=DoubleSpinBoxColumnView(
            low=0.0, high=3600.0, decimals=2, single_step=0.1,
        ),
        handler=DurationColumnHandler(),
    )
