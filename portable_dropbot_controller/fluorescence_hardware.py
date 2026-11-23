# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The fluorescence capture's driver calls (filter wheel, LED), judged the
way the dropbot-portable driver judges them: a refusal, a timeout, a FAULT
or a wheel still turning fails the stage with the driver's reason, instead
of any answer counting as success."""

# Enthought library imports.
from traits.api import HasTraits

# Local imports.
from .motion_replies import proxy_call_failure


class CaptureAborted(Exception):
    """The capture's abort event was set (abort request or disconnect)."""


class FluorescenceHardwareMixin(HasTraits):
    """Judged driver calls for the fluorescence mixin service. Composes
    into the controller, which provides ``proxy`` and ``_proxy_call``."""

    def _fluorescence_hardware_failure(self, context, call, cmd, failure, abort):
        """Run one driver call and judge its reply with ``failure`` (a
        motion_replies judge); return why it failed, or "" on success.

        A raised call with the abort set is a disconnect, which
        ``_proxy_call`` already declared and the connection observer
        turned into an abort: the run's real outcome, raised as
        CaptureAborted. The teardown passes ``abort`` None: it runs
        whatever ended the capture.
        """
        ok, reply = self._proxy_call(context, call)

        if not ok and abort is not None and abort.is_set():
            raise CaptureAborted()

        uart = getattr(self.proxy, "uart", None)

        return proxy_call_failure(ok, reply, uart, cmd, failure) or ""
