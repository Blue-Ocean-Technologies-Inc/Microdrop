"""Volume-threshold per-step column: model + view + handler + factory.

Single-file layout mirrors peripheral_protocol_controls's magnet_column
and dropbot_protocol_controls's voltage / frequency / droplet columns.

The handler is a stub in Task 5; the real on_step body lands in Task 6.
"""

from traits.api import Float

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)

from ..consts import (
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)


class VolumeThresholdColumnModel(BaseColumnModel):
    """Per-step volume threshold (user units, typically µL). 0 disables.

    Stored as a Float trait. The unit is unit-agnostic from the
    column's perspective — the handler multiplies it into the
    target-capacitance formula and the user picks the unit by
    convention with their calibration data.
    """

    def trait_for_row(self):
        return Float(float(self.default_value or 0.0),
                     desc="Volume threshold for this step. Reaches "
                          "target capacitance early-ends the phase. "
                          "0 disables.")


class VolumeThresholdColumnView(DoubleSpinBoxColumnView):
    """Numeric edit; hidden by default like droplet_check / trail knobs.
    User opts the column in via the header right-click menu when they
    want volume-threshold behaviour on a step."""

    renders_on_group = False
    hidden_by_default = True


class VolumeThresholdHandler(BaseColumnHandler):
    """Stub. Task 6 fills in the on_step body that subscribes to
    ELECTRODES_STATE_CHANGE / CAPACITANCE_UPDATED / CALIBRATION_DATA,
    computes per-phase target capacitance, and sets
    ctx.phase_advance_event when the threshold is met.

    Priority 30 puts it in the SAME parallel bucket as RoutesHandler —
    they run concurrently within the bucket so the handler can monitor
    while Routes drives the phases.
    """

    priority = 30
    wait_for_topics = []                # populated in Task 6


def make_volume_threshold_column() -> Column:
    return Column(
        model=VolumeThresholdColumnModel(
            col_id=VOLUME_THRESHOLD_COL_ID,
            col_name=VOLUME_THRESHOLD_COL_NAME,
            default_value=VOLUME_THRESHOLD_DEFAULT,
        ),
        view=VolumeThresholdColumnView(
            low=0.0, high=1_000_000.0, decimals=4, single_step=0.01,
        ),
        handler=VolumeThresholdHandler(),
    )
