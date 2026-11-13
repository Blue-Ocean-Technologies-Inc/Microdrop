# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Touch mode switch: turning it on installs the touch stylesheet block
and the touch event filter, and shows long-press tooltips as help bubbles;
turning it off undoes all three."""

# Enthought library imports.
from pyface.qt.QtCore import QTimer
from pyface.qt.QtWidgets import QApplication
from traits.api import Bool, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.helpers import apply_touch_style

# Microdrop utils imports.
from microdrop_utils.touch_long_press import set_tooltip_presenter

# Local imports.
from ..consts import TOUCH_MODE_APP_PROPERTY
from .event_filter import TouchModeEventFilter
from .help_mode import help_mode_controller

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class TouchModeController(HasTraits):
    """Applies Touch mode to the running QApplication, live."""

    #: Whether Touch mode is on.
    enabled = Bool(False)

    #: The filter installed while Touch mode is on.
    _event_filter = Instance(TouchModeEventFilter)

    #: Whether colour-scheme changes already re-colour the touch block.
    _follows_color_scheme = Bool(False)

    @observe("enabled")
    def _apply_enabled(self, event):
        if not self._follows_color_scheme:
            # Deferred: Qt may announce the scheme before the palette the
            # block is coloured from lands.
            QApplication.styleHints().colorSchemeChanged.connect(
                lambda _color_scheme: QTimer.singleShot(0, self._restyle)
            )
            self._follows_color_scheme = True

        # Set before the style changes: the StyleChange every widget then
        # gets is the cue for touch-only controls to re-read it.
        QApplication.instance().setProperty(TOUCH_MODE_APP_PROPERTY, self.enabled)

        # The filter marks widgets before the style matches them, and sizes
        # them after it applies; restoring them precedes removing it.
        if self.enabled:
            self._event_filter = TouchModeEventFilter()
            self._event_filter.install()
            apply_touch_style(True)
            self._event_filter.adapt_existing()
            set_tooltip_presenter(help_mode_controller.presenter.present_transient)

        else:
            set_tooltip_presenter(None)
            self._event_filter.uninstall()
            self._event_filter = None
            apply_touch_style(False)

        logger.info(f"Touch mode {'on' if self.enabled else 'off'}")

    def _restyle(self):
        if self.enabled:
            apply_touch_style(True)
