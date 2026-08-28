# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller for Display Scale: applies the slider to the display
server live (debounced, so a drag settles into one xrandr call), and
persists on OK / reverts on Cancel. GUI-thread only."""

from pyface.qt.QtCore import QTimer
from traits.api import Instance, Int, observe
from traitsui.api import Controller

from ..consts import DISPLAY_SCALE_APPLY_DEBOUNCE_MS
from ..models.display_scale_model import DisplayScalePreferences
from ..screen_scale import apply_live_scale, live_scaling_available

from logger.logger_service import get_logger

logger = get_logger(__name__)


class DisplayScaleController(Controller):
    """One dialog run: live-applies while it is open, then commits or
    rolls back on close."""

    #: The scale in effect when the dialog opened — what Cancel restores.
    _opening_percent = Int()

    #: Collapses a slider drag into one apply once the handle rests.
    _apply_timer = Instance(QTimer)

    def traits_init(self):
        # Explicit setup rather than a _default initializer: traits
        # cannot find a dunder-named default for an underscore-prefixed
        # trait (Python mangles ``__apply_timer_default``).
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setInterval(DISPLAY_SCALE_APPLY_DEBOUNCE_MS)
        timer.timeout.connect(self._apply_now)
        self._apply_timer = timer

    @observe("model")
    def _capture_opening_scale(self, event):
        # Controller assigns the model after construction, so the
        # scale Cancel restores is captured here, not in traits_init.
        if event.new is not None:
            self._opening_percent = event.new.scale_percent

    @observe("model:scale_percent")
    def _queue_apply(self, event):
        self._apply_timer.start()

    def _apply_now(self):
        apply_live_scale(self.model.scale_percent)

    def closed(self, info, is_ok):
        self._apply_timer.stop()

        if is_ok:
            apply_live_scale(self.model.scale_percent)
            DisplayScalePreferences().scale_percent = self.model.scale_percent
            logger.info(f"Interface scale set to {self.model.scale_percent}%")
        else:
            apply_live_scale(self._opening_percent)

        return super().closed(info, is_ok)


def apply_persisted_scale():
    """Restore the persisted scale — the plugin calls this at startup,
    since an xrandr transform does not survive a reboot."""
    if not live_scaling_available():
        return

    apply_live_scale(DisplayScalePreferences().scale_percent)
