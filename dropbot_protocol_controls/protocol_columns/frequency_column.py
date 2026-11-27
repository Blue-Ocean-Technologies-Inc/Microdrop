# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Frequency column — per-step frequency setpoint in Hertz (Int).

Mirrors voltage_column.py. Edit via Int spinbox in the protocol tree;
runtime behaviour publishes PROTOCOL_SET_FREQUENCY and waits for
FREQUENCY_APPLIED ack from dropbot_controller. Priority 20 — runs in
parallel with VoltageHandler in the same bucket.
"""

# Enthought library imports.
from traits.api import Int, TraitError

# Microdrop package imports.
from dropbot_controller.consts import (
    DEFAULT_PROTOCOL_FREQUENCY_RANGE,
    FREQUENCY_APPLIED,
    HARDWARE_MAX_FREQUENCY_KEY,
    PROTOCOL_FREQUENCY_RANGE_KEY,
    PROTOCOL_SET_FREQUENCY,
)
from dropbot_controller.preferences import DropbotPreferences
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler,
    BaseColumnModel,
    Column,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import PREFLIGHT_FREQUENCY_LIMITS_CHECK
from ..services.preflight_checks import hardware_limit_check
from .device_range_spinbox_view import DeviceRangeIntSpinBoxColumnView

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


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

        The preference is a DropBot Range (from 100 Hz), narrower than some
        devices' (the portable's 50 Hz floor), so a value outside it is
        applied to the cell but not remembered.
        """
        result = super().on_interact(row, model, value)

        try:
            DropbotPreferences().last_frequency = int(value)

        except TraitError:
            logger.info(f"Not saving {value} Hz as the last frequency: out of range")

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

    def preflight_checks(self, context):
        """Every run step's frequency against the DropBot's maximum."""
        return [
            hardware_limit_check(
                context,
                PREFLIGHT_FREQUENCY_LIMITS_CHECK,
                "Frequency",
                self.model.col_id,
                HARDWARE_MAX_FREQUENCY_KEY,
                "Hz",
            ),
        ]


def make_frequency_column():
    prefs = DropbotPreferences()
    return Column(
        model=FrequencyColumnModel(
            col_id="frequency",
            col_name="Frequency (Hz)",
            default_value=int(prefs.last_frequency),
        ),
        view=DeviceRangeIntSpinBoxColumnView(
            range_key=PROTOCOL_FREQUENCY_RANGE_KEY,
            fallback_range=DEFAULT_PROTOCOL_FREQUENCY_RANGE,
            unit="Hz",
        ),
        handler=FrequencyHandler(),
    )
