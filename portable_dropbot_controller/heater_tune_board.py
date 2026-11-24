# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The controller side of a heater tune or verify run: the board the run
loop (``heater_tune_capture``) drives, and the heater channel a request
names for its reply."""

# Standard library imports.
import json

# Enthought library imports.
from traits.api import Any, HasTraits

# Local imports.
from .consts import DEFAULT_TEMP_CHANNEL, TEMP_CHANNEL_MAX


class HeaterTuneBoard(HasTraits):
    """The board a run drives: one driver call per method, each under the
    controller's proxy lock, except OFF, which must never queue (as HV
    off). Each command method returns whether the board acknowledged it."""

    #: The composed Portable DropBot controller running the tune.
    controller = Any()

    def attached(self):
        return self.controller.proxy is not None

    def read(self, channel):
        """(current °C, output %) of a TEMP_READ_INFO, or None."""
        ok, info = self.controller._proxy_call(
            f"heater tune: read ch{channel}",
            lambda: self.controller.proxy.sig.temp_read_info(channel),
        )

        if not ok or info is None:
            return None

        return info.current, info.output

    def drive(self, channel, duty_pct):
        """Manual duty on ``channel`` (TEMP_HEAT_PWM); the other heater gets
        0, which leaves a regulating loop alone (it is off: start rule)."""
        duties = [0, 0]
        duties[channel] = duty_pct

        return self._acknowledged(
            f"heater tune: drive ch{channel} at {duty_pct} %",
            lambda: self.controller.proxy.sig.temp_heat_pwm(*duties),
        )

    def set_target(self, channel, target_c):
        """TEMP_SET_TARGET: the set point the regulated loop holds."""

        return self._acknowledged(
            f"heater tune: ch{channel} target {target_c:g} °C",
            lambda: self.controller.proxy.sig.temp_set_target(
                channel=channel, target=target_c
            ),
        )

    def start(self, channel):
        """TEMP_START_STOP 1: the regulated loop, on the board's own gains."""

        return self._acknowledged(
            f"heater tune: ch{channel} loop on",
            lambda: self.controller.proxy.sig.temp_start_stop(
                channel=channel, enable=1
            ),
        )

    def off(self, channel):
        """TEMP_START_STOP 0: ends a manual drive and a regulated loop."""

        return self._acknowledged(
            f"heater tune: ch{channel} off",
            lambda: self.controller.proxy.sig.temp_start_stop(
                channel=channel, enable=0
            ),
            serialize=False,
        )

    def _acknowledged(self, context, call, serialize=True):
        ok, accepted = self.controller._proxy_call(context, call, serialize=serialize)

        return bool(ok and accepted)


def heater_request_channel(message):
    """The heater channel a (possibly invalid) request names, for its reply;
    the default channel when it names none."""
    try:
        channel = int(json.loads(str(message)).get("channel", DEFAULT_TEMP_CHANNEL))
    except (ValueError, TypeError, AttributeError):
        return DEFAULT_TEMP_CHANNEL

    return min(max(channel, 0), TEMP_CHANNEL_MAX)
