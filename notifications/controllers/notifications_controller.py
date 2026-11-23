# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pane's requests turned into changes: read, clear, dismiss, run an
entry's action, and show or hide the pane. Qt-free: the pane is reached
through its ``reveal()``, ``conceal()`` and ``showing_contents``."""

# Enthought library imports.
from traits.api import Callable, HasTraits, Instance, observe
from traits.observation.api import trait

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import PKG, SEVERITY_ERROR, OpenPathAction, PublishAction
from ..models.notifications_pane_model import NotificationsPaneModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NotificationsController(HasTraits):
    """Acts on the pane model's requests and on show/hide requests."""

    #: The pane's state.
    pane_model = Instance(NotificationsPaneModel, ())

    #: The dock pane once created: has ``reveal()``, ``conceal()`` and a
    #: ``showing_contents`` Bool. None in a standalone view.
    pane = Instance(HasTraits)

    #: ``publish(topic=..., message=...)`` for a PublishAction.
    publish = Callable(publish_message)

    #: ``open_path(path)`` for an OpenPathAction.
    open_path = Callable()

    def _open_path_default(self):
        # Imported on first use: it brings webbrowser with it.
        from microdrop_utils.file_handler import open_file

        return open_file

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def toggle_pane(self):
        """Hide the pane if it is on screen, else show and raise it."""

        if self.pane is None:
            return

        if self.pane.showing_contents:
            self.pane.conceal()

        else:
            self.pane.reveal()

    def show_pane(self, section_id=""):
        """Show and raise the pane, expanding ``section_id`` if given."""

        if section_id:
            self.pane_model.expand_section(section_id)

        if self.pane is not None:
            self.pane.reveal()

    # ------------------------------------------------------------------ #
    # Reactions                                                           #
    # ------------------------------------------------------------------ #

    @observe("pane_model:mark_all_read_button")
    def _mark_all_read(self, event):
        self.pane_model.center.mark_all_read()

    @observe("pane_model:clear_all_button")
    def _clear_all(self, event):
        self.pane_model.center.clear()

    @observe("pane_model:dismiss")
    def _dismiss(self, event):
        self.pane_model.center.dismiss(event.new)

    @observe("pane_model:run_action")
    def _run_action(self, event):
        action = event.new.action

        if isinstance(action, PublishAction):
            # The topic is the poster's, so it has no validated publisher here.
            self.publish(topic=action.topic, message=action.message)

        elif isinstance(action, OpenPathAction):
            try:
                self.open_path(action.path)

            # Shown where the user pressed the button; the log forwarder
            # skips this plugin's own records.
            except OSError as error:
                logger.error(f"Could not open {action.path}: {error}")
                self.pane_model.center.post(
                    f"Could not open {action.path}",
                    detail=str(error),
                    severity=SEVERITY_ERROR,
                    source=PKG,
                )

    @observe(trait("pane", notify=False).trait("showing_contents", optional=True))
    @observe("pane_model:center:unread_count")
    def _read_while_showing(self, event):
        """What arrives while the list is on screen counts as seen."""

        if self.pane is not None and self.pane.showing_contents:
            self.pane_model.center.mark_all_read()
