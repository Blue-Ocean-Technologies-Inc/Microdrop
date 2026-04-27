"""Voltage column — per-step voltage setpoint in volts (Int).

Edit via Int spinbox in the protocol tree; runtime behaviour publishes
PROTOCOL_SET_VOLTAGE and waits for VOLTAGE_APPLIED ack from
dropbot_controller. Priority 20 — runs before RoutesHandler at
priority 30 so the voltage is applied before any electrode actuation.
"""
from traits.api import Int

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView

from dropbot_controller.consts import HARDWARE_MIN_VOLTAGE
from dropbot_controller.preferences import DropbotPreferences

# Static spinbox upper. Hardware-reported max isn't known at column
# construction time (DropBot reports via app_globals only after connect),
# and the trait can't be re-bounded after instantiation. The backend
# validates the actual write against proxy.config.max_voltage anyway.
_DEFAULT_HARDWARE_MAX_V = 140  # DropBot DB3-120 nominal max


class VoltageColumnModel(BaseColumnModel):
    """Per-step voltage setpoint stored as an Int on each row."""

    def trait_for_row(self):
        return Int(int(self.default_value), desc="Step voltage in V")


def make_voltage_column():
    prefs = DropbotPreferences()
    return Column(
        model=VoltageColumnModel(
            col_id="voltage",
            col_name="Voltage (V)",
            default_value=int(prefs.last_voltage),
        ),
        view=IntSpinBoxColumnView(
            low=HARDWARE_MIN_VOLTAGE, high=_DEFAULT_HARDWARE_MAX_V,
        ),
        handler=BaseColumnHandler(),  # replaced in tasks 5 + 6
    )
