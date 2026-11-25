# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's requests turned into changes: read, clear, dismiss, a card's
buttons, and opening or closing the drawer. Qt-free: the views follow the
model."""

# Enthought library imports.
from traits.api import Callable, HasTraits, Instance, observe

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    PKG,
    SEVERITY_ERROR,
    HelpAction,
    OpenPathAction,
    PublishAction,
    SnoozeAction,
)
from ..models.notification import link_folder
from ..models.notifications_pane_model import NotificationsPaneModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NotificationsController(HasTraits):
    """Acts on the pane model's requests and on open/close requests."""

    #: The drawer's state.
    pane_model = Instance(NotificationsPaneModel, ())

    #: ``publish(topic=..., message=...)`` for a PublishAction.
    publish = Callable(publish_message)

    #: ``open_path(path)`` for an OpenPathAction.
    open_path = Callable()

    #: ``open_help(target)`` for a HelpAction; None while nothing can open
    #: help, which disables the help links.
    open_help = Callable()

    def _open_path_default(self):
        # Imported on first use: it brings webbrowser with it.
        from microdrop_utils.file_handler import open_file

        return open_file

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def toggle_pane(self):
        """Close the drawer if it is open, else open it."""
        self.pane_model.is_open = not self.pane_model.is_open

    def show_pane(self, section_id="", by_app=False):
        """Open the drawer, expanding ``section_id`` if given; ``by_app``
        when the app opens it, not the user (``opened_by_app``)."""
        model = self.pane_model

        if section_id:
            model.expand_section(section_id)

        if not model.is_open:
            model.opened_by_app = by_app

        model.is_open = True

    # ------------------------------------------------------------------ #
    # The header's buttons                                                #
    # ------------------------------------------------------------------ #

    @observe("pane_model:mark_all_read_button")
    def _mark_all_read(self, event):
        """Read everything, and drop the open drawer's "new" marks too."""
        center = self.pane_model.center
        marked = [entry for entry in center.entries if entry.unread or entry.is_new]

        center.update_all(marked, unread=False, is_new=False)

    @observe("pane_model:clear_all_button")
    def _clear_all(self, event):
        self.pane_model.center.clear()

    @observe("pane_model:close_button")
    def _close(self, event):
        self.pane_model.is_open = False

    @observe("pane_model:dismiss")
    def _dismiss(self, event):
        self.pane_model.center.dismiss(event.new)

    # ------------------------------------------------------------------ #
    # A card's buttons                                                    #
    # ------------------------------------------------------------------ #

    @observe("pane_model:run_action")
    def _run_action(self, event):
        """Do what the button says; the card then counts as handled: read,
        out of Needs attention, its buttons replaced by what was done."""
        entry = event.new
        action = entry.action

        # Handled first, so its toast has left before any answer arrives.
        entry.trait_set(acted=action.label, needs_attention=False, unread=False)

        if isinstance(action, PublishAction):
            # The topic is the poster's, so it has no validated publisher here.
            self.publish(topic=action.topic, message=action.message)

        elif isinstance(action, OpenPathAction):
            self._open(action.path)

    @observe("pane_model:run_secondary_action")
    def _run_secondary_action(self, event):
        entry = event.new
        action = entry.secondary_action

        # Help: read, yet still to do, so it stays in Needs attention until
        # dismissed or its condition clears.
        if isinstance(action, HelpAction) and self.open_help is not None:
            entry.unread = False
            self.open_help(action.target)

        # Later: out of Needs attention, into Activity, still to do.
        elif isinstance(action, SnoozeAction):
            entry.trait_set(needs_attention=False, unread=False)

    @observe("pane_model:open_link")
    def _open_link(self, event):
        """A detail link opens its folder in the file manager: a file's link
        the folder holding it, so a link never runs a file."""
        self._open(str(link_folder(event.new)))

    @observe("open_help")
    def _follow_help_handler(self, event):
        self.pane_model.help_available = self.open_help is not None

    def _open(self, path):

        try:
            self.open_path(path)

        # Shown where the user pressed the button; the log forwarder skips
        # this plugin's own records.
        except OSError as error:
            logger.error(f"Could not open {path}: {error}")
            self.pane_model.center.post(
                f"Could not open {path}",
                detail=str(error),
                severity=SEVERITY_ERROR,
                source=PKG,
            )

    # ------------------------------------------------------------------ #
    # Reading                                                             #
    # ------------------------------------------------------------------ #

    # Events and plain traits, not a count: a count changed again while its
    # change is announced can leave later observers stale (#1134).
    @observe("pane_model:is_open")
    @observe("pane_model:center:[arrived, repeated]")
    def _read_while_open(self, event):
        """Opening the drawer marks the unread entries seen, and new until it
        closes; what arrives while it is open is new too. Closing it drops
        the marks."""
        center = self.pane_model.center
        is_open = self.pane_model.is_open

        if event.name != "is_open":
            if is_open and event.new.unread:
                event.new.trait_set(is_new=True, unread=False)

            return

        if is_open:
            unread = [entry for entry in center.entries if entry.unread]
            center.update_all(unread, is_new=True, unread=False)

        else:
            marked = [entry for entry in center.entries if entry.is_new]
            center.update_all(marked, is_new=False)
