# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.action.api import StatusBarManager as _StatusBarManager
from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QApplication, QLabel, QStatusBar
from pyface.tasks.dock_pane import DockPane

# Microdrop style imports.
from microdrop_style.helpers import QT_THEME_NAMES, is_dark_mode
from microdrop_style.label_style import get_label_style
from microdrop_style.status_bar_style import get_status_bar_stylesheet

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


# The outer layer accepts the decorator arguments
def app_statusbar_message_from_dock_pane(message: str):
    """
    Display a status message. Use for a class method within a dock pane
    """

    def decorator(func):
        def wrapper(dock_pane: "DockPane", *args, **kwargs):
            # 1. Access the manager
            _status_bar_manager = dock_pane.task.window.status_bar_manager

            # 2. Set the message
            # This triggers the trait observer -> signal -> QStatusBar.showMessage
            # However, the screen pixels won't update yet!
            _status_bar_manager.messages += [message]

            # 3. FORCE THE UI UPDATE
            # This tells Qt to run the event loop and process the "repaint"
            # events sitting in the queue right now.
            QApplication.processEvents()

            try:
                # 4. Run the actual blocking function
                result = func(dock_pane, *args, **kwargs)
                return result
            finally:
                # 5. Cleanup (in finally block so it runs even if func errors)
                # Note: using replace on the current message handles cases where
                # other messages might have been appended in the meantime.
                _status_bar_manager.remove(message)

        return wrapper

    return decorator


class StatusBarManager(_StatusBarManager):
    """A status bar manager realizes itself in a status bar control."""

    # ------------------------------------------------------------------------
    # 'StatusBarManager' interface.
    # ------------------------------------------------------------------------

    def create_status_bar(self, parent):
        """Creates a status bar."""

        if self.status_bar is None:
            self.status_bar = QStatusBar(parent)
            self.status_bar.setSizeGripEnabled(self.size_grip)
            self.status_bar.setVisible(self.visible)

            self.persistent_label = QLabel("")
            self.status_bar.addWidget(self.persistent_label)

        # initial values
        if len(self.messages) > 1:
            self._show_messages()
        else:
            self.persistent_label.setText(self.message)

        # ------------------- Theme aware styling -------------------#
        def _apply_theme_style(theme: "Qt.ColorScheme"):
            """Handle theme updates"""
            theme = QT_THEME_NAMES[theme]

            status_bar_style = get_status_bar_stylesheet(theme)
            label_style = get_label_style(theme)

            self.status_bar.setStyleSheet(f"{status_bar_style}\n{label_style}")

        # Apply initial theme styling
        _apply_theme_style(
            theme=Qt.ColorScheme.Dark if is_dark_mode() else Qt.ColorScheme.Light
        )
        # Call theme application method whenever global theme changes occur as well
        QApplication.styleHints().colorSchemeChanged.connect(_apply_theme_style)

        # -----------------------------------------------------------#

        return self.status_bar

    def remove(self, message):
        """Remove a message from the status bar."""

        self.messages = [msg for msg in self.messages if msg != message]

    # ------------------------------------------------------------------------
    # Private interface.
    # ------------------------------------------------------------------------

    def _show_messages(self):
        """Display the list of messages."""

        # FIXME v3: At the moment we just string them together but we may
        # decide to put all but the first message into separate widgets.  We
        # probably also need to extend the API to allow a "message" to be a
        # widget - depends on what wx is capable of.
        # An empty first message (no mode text) must not lead with a tab.
        self.persistent_label.setText("\t".join(filter(None, self.messages)))
