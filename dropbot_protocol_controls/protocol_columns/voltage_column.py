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

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import (
    HARDWARE_MIN_VOLTAGE, PROTOCOL_SET_VOLTAGE, VOLTAGE_APPLIED,
)
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


class VoltageHandler(BaseColumnHandler):
    """Publishes the row's voltage setpoint and waits for the dropbot ack.

    Priority 20 — runs in parallel with FrequencyHandler in the same
    bucket, and strictly before RoutesHandler at priority 30. The
    timeout matches RoutesHandler's: 5.0s of headroom for cold-broker
    first-publish (~1-2s) and worker-queue contention.
    """
    priority = 20
    wait_for_topics = [VOLTAGE_APPLIED]

    def on_interact(self, row, model, value):
        """User edited a voltage cell — write through AND persist to prefs.

        DropbotPreferences() with no args attaches to the global preferences
        object set during envisage startup (PreferencesHelper convention,
        see dropbot_controller/preferences.py:22-25). Storing here means
        the next session's status-panel boot value matches the last
        cell-edit, just like editing the spinner in the dropbot status panel.
        """
        super().on_interact(row, model, value)
        DropbotPreferences().last_voltage = int(value)

    def on_step(self, row, ctx):
        v = int(row.voltage)
        publish_message(topic=PROTOCOL_SET_VOLTAGE, message=str(v))
        ctx.wait_for(VOLTAGE_APPLIED, timeout=5.0)


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
        handler=VoltageHandler(),
    )
