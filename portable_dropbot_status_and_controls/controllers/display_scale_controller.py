# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller for Display Scale: the slider only picks a value — Apply
commits it to the screen and the preferences, Reset returns the panel
to its native 100%. GUI-thread only."""

from traits.api import observe
from traitsui.api import Controller

from ..consts import DISPLAY_SCALE_DEFAULT_PERCENT
from ..models.display_scale_model import DisplayScalePreferences
from ..screen_scale import apply_live_scale, live_scaling_available

from logger.logger_service import get_logger

logger = get_logger(__name__)


class DisplayScaleController(Controller):
    """Buttons -> display server + preferences; the slider itself
    changes nothing."""

    @observe("model:apply_button")
    def _apply(self, event):
        self._commit(self.model.scale_percent)

    @observe("model:reset_button")
    def _reset(self, event):
        self.model.scale_percent = DISPLAY_SCALE_DEFAULT_PERCENT
        self._commit(DISPLAY_SCALE_DEFAULT_PERCENT)

    @staticmethod
    def _commit(percent):
        if apply_live_scale(percent):
            DisplayScalePreferences().scale_percent = percent
            logger.info(f"Interface scale set to {percent}%")


def apply_persisted_scale():
    """Restore the persisted scale — the plugin calls this at startup,
    since an xrandr transform does not survive a reboot."""
    if not live_scaling_available():
        return

    apply_live_scale(DisplayScalePreferences().scale_percent)
