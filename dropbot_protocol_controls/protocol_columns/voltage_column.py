# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Voltage column — per-step voltage setpoint in volts (Int).

Edit via Int spinbox in the protocol tree; runtime behaviour publishes
PROTOCOL_SET_VOLTAGE and waits for VOLTAGE_APPLIED ack from
dropbot_controller. Priority 20 — runs before RoutesHandler at
priority 30 so the voltage is applied before any electrode actuation.
"""

# Microdrop package imports.
from dropbot_controller.consts import (
    DEFAULT_PROTOCOL_VOLTAGE_RANGE,
    PROTOCOL_SET_VOLTAGE,
    PROTOCOL_VOLTAGE_RANGE_KEY,
    VOLTAGE_APPLIED,
)
from dropbot_controller.preferences import DropbotPreferences
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler,
    Column,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import PREFLIGHT_VOLTAGE_LIMITS_CHECK
from ..services.preflight_checks import (
    chip_check,
    device_range_check,
    dropbot_connection_check,
)
from .device_range_model import DeviceRangeIntColumnModel, remember_last_setpoint
from .device_range_spinbox_view import DeviceRangeIntSpinBoxColumnView


class VoltageColumnModel(DeviceRangeIntColumnModel):
    """Per-step voltage setpoint stored as an Int on each row."""

    range_key = PROTOCOL_VOLTAGE_RANGE_KEY
    fallback_range = DEFAULT_PROTOCOL_VOLTAGE_RANGE


class VoltageHandler(BaseColumnHandler):
    """Publishes the row's voltage setpoint and waits for the dropbot ack.

    Priority 20 — runs in parallel with FrequencyHandler in the same
    bucket, and strictly before RoutesHandler at priority 30. The ack
    wait comes from the Protocol Settings grid (0 = fire-and-forget).
    """

    priority = 20
    wait_for_topics = [VOLTAGE_APPLIED]
    # Provider default for the Protocol Settings ack-wait grid — matches
    # RoutesHandler's: 5.0s of headroom for cold-broker first-publish
    # (~1-2s) and worker-queue contention.
    default_ack_time_s = 5.0

    def on_interact(self, row, model, value):
        """User edited a voltage cell — write through AND persist to prefs.

        DropbotPreferences() with no args attaches to the global preferences
        object set during envisage startup (PreferencesHelper convention,
        see dropbot_controller/preferences.py:22-25). Storing here means
        the next session's status-panel boot value matches the last
        cell-edit, just like editing the spinner in the dropbot status panel.

        Must return the super's return value so QtTreeModel.setData
        signals dataChanged and the manager fires rows_changed — without
        it the protocol state tracker never sees voltage edits.
        """
        result = super().on_interact(row, model, value)
        remember_last_setpoint(DropbotPreferences(), "last_voltage", value, "V")

        return result

    def on_step(self, row, ctx):
        # Preview mode: skip the hardware-publish + ack-wait. The
        # DropBot voltage RPC isn't sent and no VOLTAGE_APPLIED comes
        # back. Mirrors the legacy protocol_grid Preview Mode.
        if getattr(ctx.protocol, "preview_mode", False):
            return
        v = int(row.voltage)
        publish_message(topic=PROTOCOL_SET_VOLTAGE, message=str(v))
        if self.ack_time_s > 0:
            ctx.wait_for(VOLTAGE_APPLIED, timeout=self.ack_time_s)

    def on_live_edit(self, row, ctx):
        # Advanced-mode edit to the running step's voltage (#434): re-apply
        # the new setpoint now. Fire-and-forget (GUI thread — no mailbox to
        # wait on); the next on_step would re-publish anyway. Preview skips,
        # same as on_step. ctx is the ProtocolContext (preview_mode direct).
        if getattr(ctx, "preview_mode", False):
            return
        publish_message(topic=PROTOCOL_SET_VOLTAGE, message=str(int(row.voltage)))

    def preflight_checks(self, context):
        """The DropBot's connection and chip, and every run step's voltage against
        the device range its cells are bounded by."""
        return [
            dropbot_connection_check(context),
            chip_check(context),
            device_range_check(
                context,
                PREFLIGHT_VOLTAGE_LIMITS_CHECK,
                "Voltage",
                self.model.col_id,
                self.model.device_range(),
                "V",
            ),
        ]


def make_voltage_column():
    prefs = DropbotPreferences()
    return Column(
        model=VoltageColumnModel(
            col_id="voltage",
            col_name="Voltage (V)",
            default_value=int(prefs.last_voltage),
        ),
        view=DeviceRangeIntSpinBoxColumnView(unit="V"),
        handler=VoltageHandler(),
    )
