"""Heater temperature compound column — drives a heater to a target temperature
for a protocol step and blocks the step until the PID temperature is within a
tolerance band of the target.

Two coupled cells share one model + one handler (the PPT-11 compound framework):
  * target_temperature_c (Float) — the PID setpoint to drive toward
  * tolerance_c          (Float) — the +/- band that counts as "reached"

The handler publishes PROTOCOL_SET_TEMPERATURE; the heater backend sets the
target, watches the PID telemetry, and acks on TEMPERATURE_REACHED once within
tolerance — which the step's ``ctx.wait_for`` is blocking on.
"""
import json

from traits.api import Float

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from heater_controller.consts import (
    PROTOCOL_SET_TEMPERATURE, TEMPERATURE_REACHED, DEFAULT_HEATER,
)
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.spinbox import DoubleSpinBoxColumnView

# Sensible defaults / spinbox ranges (mirror the heater UI's setpoint range).
TARGET_DEFAULT = 40.0
TOLERANCE_DEFAULT = 1.0
TARGET_MIN, TARGET_MAX = 0.0, 150.0
TOLERANCE_MIN, TOLERANCE_MAX = 0.0, 20.0


class TemperatureCompoundModel(BaseCompoundColumnModel):
    """Two coupled fields; base_id 'heater_temperature' appears as the compound
    id on each field's JSON column entry."""
    base_id = "heater_temperature"

    def field_specs(self):
        return [
            FieldSpec("target_temperature_c", "Target Temp (°C)", TARGET_DEFAULT),
            FieldSpec("tolerance_c", "Tolerance (°C)", TOLERANCE_DEFAULT),
        ]

    def trait_for_field(self, field_id):
        if field_id == "target_temperature_c":
            return Float(TARGET_DEFAULT)
        if field_id == "tolerance_c":
            return Float(TOLERANCE_DEFAULT)
        raise KeyError(field_id)


class TemperatureHandler(BaseCompoundColumnHandler):
    """Publishes the step's target + tolerance and waits for the reached ack.

    Priority 20 — same bucket as voltage/frequency/magnet, before routes (30).
    The ack wait comes from the Protocol Settings grid; set it to 0 there to run
    fire-and-forget (set the target without blocking).
    """
    priority = 20
    wait_for_topics = [TEMPERATURE_REACHED]
    # Heating/cooling to a setpoint is slow, so default the ack-wait higher than
    # voltage/frequency (5 s) or magnet (10 s).
    default_ack_time_s = 120.0

    def on_step(self, row, ctx):
        if getattr(ctx.protocol, "preview_mode", False):
            return
        publish_message(
            topic=PROTOCOL_SET_TEMPERATURE,
            message=json.dumps({
                "heater": DEFAULT_HEATER,
                "temperature": float(row.target_temperature_c),
                "tolerance": float(row.tolerance_c),
            }),
        )
        if self.ack_time_s > 0:
            ctx.wait_for(TEMPERATURE_REACHED, timeout=self.ack_time_s)


def make_temperature_column():
    """Factory — a fresh heater-temperature CompoundColumn."""
    return CompoundColumn(
        model=TemperatureCompoundModel(),
        view=DictCompoundColumnView(cell_views={
            "target_temperature_c": DoubleSpinBoxColumnView(
                low=TARGET_MIN, high=TARGET_MAX, decimals=1, single_step=1.0),
            "tolerance_c": DoubleSpinBoxColumnView(
                low=TOLERANCE_MIN, high=TOLERANCE_MAX, decimals=1, single_step=0.5),
        }),
        handler=TemperatureHandler(),
    )
