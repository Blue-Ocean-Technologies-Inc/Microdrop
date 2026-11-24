# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A news publisher's Demo submenu: its feed creator, reload, and pushes.

The same actions as the notifications_pane demo's feed toolbar, aimed at one
publisher's section and feed file: the creator opens on that file and sends
to that section.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from pyface.action.api import Action
from pyface.tasks.action.api import SMenu
from traits.api import Callable, HasTraits, Instance, Int, List

# Microdrop package imports.
from examples.demos.notifications_pane.feed_creator import open_feed_creator
from examples.demos.notifications_pane.sci_bots_feed_demo import (
    JSON_WILDCARD,
    SAMPLE_PUSH_POST,
)
from microdrop_application.dialogs.pyface_wrapper import file_dialog

# Local imports.
from .publishers import NewsSection


class NewsFeedActions(HasTraits):
    """What the Demo menu does to one publisher's feed."""

    #: The publisher's section; its controller fills the feed.
    section = Instance(NewsSection)

    #: ``window()``: the main window's control, the dialogs' parent.
    window = Callable(lambda: None)

    #: Open creators, held so they stay open.
    _creators = List()

    #: Sample posts pushed so far, for their ids.
    _pushed = Int(0)

    def menu(self):
        """The publisher's submenu."""
        publisher = self.section.publisher

        return SMenu(
            Action(name="Feed creator…", on_perform=self.open_creator),
            Action(name="Reload feed", on_perform=self.section.controller.reload),
            Action(name="Push post from JSON…", on_perform=self.push_from_file),
            Action(name="Push sample post", on_perform=self.push_sample),
            id=f"notifications_ux_demo.news.{publisher.id}",
            name=publisher.short_name,
        )

    def open_creator(self):
        """The feed creator on the publisher's feed file, able to send to
        its section."""
        self._creators = [ui for ui in self._creators if ui.control is not None]
        self._creators.append(
            open_feed_creator(
                self.section.publisher.feed_path,
                feed_controller=self.section.controller,
                parent=None,
            )
        )

    def push_from_file(self):
        """Push a post or feed chosen in a file dialog."""
        path = file_dialog(
            parent=self.window(),
            default_path=str(Path(self.section.publisher.feed_path).parent),
            wildcard=JSON_WILDCARD,
        )

        if path:
            self.section.controller.push_file(path)
            self.section.expanded = True

    def push_sample(self):
        """Push the demo's placeholder post, under a new id each time, so
        each push is a new post and alerts."""
        publisher = self.section.publisher
        self._pushed += 1

        self.section.controller.push(
            {
                **SAMPLE_PUSH_POST,
                "id": f"{SAMPLE_PUSH_POST['id']}-{publisher.id}-{self._pushed}",
                "source": publisher.full_name,
                "summary": "Sample content pushed from the Demo menu.",
                "summary_html": "",
                "url": publisher.home_url,
            }
        )
