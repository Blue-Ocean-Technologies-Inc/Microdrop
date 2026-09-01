# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Temperature compound column — drives the portable instrument's
built-in heater channel to a target temperature for a protocol step and
blocks the step until the reading is within a tolerance band of the
target.

Three coupled cells share one model + one handler (the PPT-11 compound
framework):
  * set_temperature      (Bool)  — drive the heater on this step, or leave
    it untouched (unchecked = no setpoint publish, no reached-ack wait)
  * target_temperature_c (Float) — the setpoint to drive toward
  * tolerance_c          (Float) — the +/- band that counts as "reached"

For a checked step the handler publishes PROTOCOL_SET_TEMPERATURE; the
portable backend sets the target, turns temperature control on, watches
the channel reading, and acks on TEMPERATURE_REACHED once within
tolerance — which the step's ``ctx.wait_for`` is blocking on.
"""

# Standard library imports.
import json

# Enthought library imports.
from pyface.qt.QtCore import Qt
from traits.api import Bool, Float

# Microdrop package imports.
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
    BaseCompoundColumnModel,
    CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)
from portable_dropbot_controller.consts import (
    DEFAULT_TEMP_CHANNEL,
    PROTOCOL_SET_TEMPERATURE,
    TEMP_CONTROL,
    TEMP_TARGET_C_BOUNDS,
    TEMPERATURE_REACHED,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import SET_TEMPERATURE_FIELD_ID

# Sensible defaults / spinbox ranges (mirror the temp & lighting pane's
# setpoint range).
TARGET_DEFAULT = 40.0
TOLERANCE_DEFAULT = 1.0
TARGET_MIN, TARGET_MAX = TEMP_TARGET_C_BOUNDS
TOLERANCE_MIN, TOLERANCE_MAX = 0.0, 20.0


class TemperatureCompoundModel(BaseCompoundColumnModel):
    """Three coupled fields; base_id 'heater_temperature' appears as the
    compound id on each field's JSON column entry."""

    base_id = "heater_temperature"

    def field_specs(self):
        return [
            FieldSpec(SET_TEMPERATURE_FIELD_ID, "Set Temp", False),
            FieldSpec("target_temperature_c", "Target Temp (°C)", TARGET_DEFAULT),
            FieldSpec("tolerance_c", "Tolerance (°C)", TOLERANCE_DEFAULT),
        ]

    def trait_for_field(self, field_id):
        if field_id == SET_TEMPERATURE_FIELD_ID:
            return Bool(False)
        if field_id == "target_temperature_c":
            return Float(TARGET_DEFAULT)
        if field_id == "tolerance_c":
            return Float(TOLERANCE_DEFAULT)
        raise KeyError(field_id)


class TemperatureSetpointSpinBoxView(DoubleSpinBoxColumnView):
    """Setpoint cell that is read-only while the step's Set Temp checkbox
    is off (cross-cell editability via the canonical PPT-11 get_flags(row)
    pattern, mirroring the magnet column's height cell)."""

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, SET_TEMPERATURE_FIELD_ID, False):
            flags &= ~Qt.ItemIsEditable
        return flags


class TemperatureHandler(BaseCompoundColumnHandler):
    """Publishes the step's target + tolerance and waits for the reached ack.

    Priority 20 — same bucket as the magnet column, before routes (30).
    The ack wait comes from the Protocol Settings grid; set it to 0 there
    to run fire-and-forget (set the target without blocking).
    """

    priority = 20
    wait_for_topics = [TEMPERATURE_REACHED]
    # Heating/cooling to a setpoint is slow, so default the ack-wait higher
    # than the magnet column's (40 s).
    default_ack_time_s = 120.0

    def on_step(self, row, ctx):
        if getattr(ctx.protocol, "preview_mode", False):
            return
        # Unchecked = the step leaves the heater untouched: no setpoint
        # publish, no reached-ack wait.
        if not getattr(row, SET_TEMPERATURE_FIELD_ID, False):
            return
        publish_message(
            topic=PROTOCOL_SET_TEMPERATURE,
            message=json.dumps(
                {
                    "channel": DEFAULT_TEMP_CHANNEL,
                    "target_c": float(row.target_temperature_c),
                    "tolerance_c": float(row.tolerance_c),
                }
            ),
        )
        if self.ack_time_s > 0:
            ctx.wait_for(TEMPERATURE_REACHED, timeout=self.ack_time_s)

    def on_post_protocol_end(self, ctx):
        """Turn the heater channel off — unconditional at the end of every
        run (normal or aborted), so nothing keeps heating unattended after
        the protocol finishes."""
        if getattr(ctx, "preview_mode", False):
            return
        publish_message(
            topic=TEMP_CONTROL,
            message=json.dumps({"channel": DEFAULT_TEMP_CHANNEL, "on": False}),
        )


def make_temperature_column():
    """Factory — a fresh portable heater-temperature CompoundColumn."""
    return CompoundColumn(
        model=TemperatureCompoundModel(),
        view=DictCompoundColumnView(
            cell_views={
                SET_TEMPERATURE_FIELD_ID: CheckboxColumnView(),
                "target_temperature_c": TemperatureSetpointSpinBoxView(
                    low=TARGET_MIN, high=TARGET_MAX, decimals=1, single_step=1.0
                ),
                "tolerance_c": TemperatureSetpointSpinBoxView(
                    low=TOLERANCE_MIN, high=TOLERANCE_MAX, decimals=1, single_step=0.5
                ),
            }
        ),
        handler=TemperatureHandler(),
    )
