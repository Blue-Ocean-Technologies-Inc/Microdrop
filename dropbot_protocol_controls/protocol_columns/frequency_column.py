"""Frequency column — per-step frequency setpoint in Hertz (Int).

Mirrors voltage_column.py. Edit via Int spinbox in the protocol tree;
runtime behaviour publishes PROTOCOL_SET_FREQUENCY and waits for
FREQUENCY_APPLIED ack from dropbot_controller. Priority 20 — runs in
parallel with VoltageHandler in the same bucket.
"""
from traits.api import Int

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import (
    HARDWARE_MIN_FREQUENCY, PROTOCOL_SET_FREQUENCY, FREQUENCY_APPLIED,
)
from dropbot_controller.preferences import DropbotPreferences

# Static spinbox upper. Hardware-reported max isn't known at column
# construction time. Backend validates against proxy.config.max_frequency.
# 100_000 Hz matches dropbot_preferences_ui/models.py's ui_max_frequency
# Range high (the UI already lets users raise prefs.last_frequency above
# 10 kHz) — using a lower cap here would silently clamp those edits.
_DEFAULT_HARDWARE_MAX_HZ = 100_000


class FrequencyColumnModel(BaseColumnModel):
    """Per-step frequency setpoint stored as an Int on each row."""

    def trait_for_row(self):
        return Int(int(self.default_value), desc="Step frequency in Hz")


class FrequencyHandler(BaseColumnHandler):
    """Publishes the row's frequency setpoint and waits for the dropbot ack.

    Priority 20 — runs in parallel with VoltageHandler in the same bucket,
    and strictly before RoutesHandler at priority 30. The ack wait comes
    from the Protocol Settings grid (0 = fire-and-forget).
    """
    priority = 20
    wait_for_topics = [FREQUENCY_APPLIED]
    # Provider default for the Protocol Settings ack-wait grid — matches
    # VoltageHandler's 5.0s.
    default_ack_time_s = 5.0

    def on_interact(self, row, model, value):
        """User edited a frequency cell — write through AND persist to prefs.

        Must return the super's return value so the delegate fires
        dataChanged and the manager fires rows_changed — without it the
        protocol state tracker never sees frequency edits.
        """
        result = super().on_interact(row, model, value)
        DropbotPreferences().last_frequency = int(value)
        return result

    def on_step(self, row, ctx):
        # Preview mode: skip the hardware-publish + ack-wait.
        # Mirrors the legacy protocol_grid Preview Mode.
        if getattr(ctx.protocol, "preview_mode", False):
            return
        v = int(row.frequency)
        publish_message(topic=PROTOCOL_SET_FREQUENCY, message=str(v))
        if self.ack_time_s > 0:
            ctx.wait_for(FREQUENCY_APPLIED, timeout=self.ack_time_s)

    def on_live_edit(self, row, ctx):
        # Advanced-mode edit to the running step's frequency (#434): re-apply
        # the new setpoint now, fire-and-forget. Preview skips, like on_step.
        # ctx is the ProtocolContext (preview_mode is a direct attribute).
        if getattr(ctx, "preview_mode", False):
            return
        publish_message(topic=PROTOCOL_SET_FREQUENCY, message=str(int(row.frequency)))


def make_frequency_column():
    prefs = DropbotPreferences()
    return Column(
        model=FrequencyColumnModel(
            col_id="frequency",
            col_name="Frequency (Hz)",
            default_value=int(prefs.last_frequency),
        ),
        view=IntSpinBoxColumnView(
            low=HARDWARE_MIN_FREQUENCY, high=_DEFAULT_HARDWARE_MAX_HZ,
        ),
        handler=FrequencyHandler(),
    )
