# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Demo menu's News actions: reload and pushes.

Aimed at the news plugin's News section, fetched when used (the plugin
loads after the window paints).
"""

# Enthought library imports.
from pyface.action.api import Action
from traits.api import Callable, HasTraits, Int

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import file_dialog
from news.consts import FEED_PATH

#: What Push sample post sends: a placeholder with rich text.
SAMPLE_PUSH_POST = {
    "id": "demo-sample-push",
    "title": "PLACEHOLDER pushed post — rich text sample",
    "date": "2026-11-23",
    "kind": "announcement",
    "source": "Demo push",
    "summary": "Sample content pushed from the Demo menu.",
    "summary_html": (
        "<p><b>Sample content</b> pushed from the Demo menu, with a "
        '<a href="https://www.linkedin.com/company/sci-bots-inc./posts/">link</a>'
        " and a list:</p><ul><li>first point</li><li><i>second</i> point</li>"
        "</ul>"
    ),
    "url": "https://www.linkedin.com/company/sci-bots-inc./posts/",
}

#: The file dialog's filter for feed and post JSON files.
JSON_WILDCARD = "JSON files (*.json)"


class NewsFeedActions(HasTraits):
    """What the Demo menu does to the News feed."""

    #: ``get_section()``: the News section, or None while the news plugin
    #: is not loaded (it loads after the window paints).
    get_section = Callable(lambda: None)

    #: ``window()``: the main window's control, the dialogs' parent.
    window = Callable(lambda: None)

    #: Sample posts pushed so far, for their ids.
    _pushed = Int(0)

    def actions(self):
        """The menu items."""
        return [
            Action(name="Reload feed", on_perform=self.reload),
            Action(name="Push post from JSON…", on_perform=self.push_from_file),
            Action(name="Push sample post", on_perform=self.push_sample),
        ]

    @property
    def section(self):
        """The News section; actions do nothing while there is none."""
        return self.get_section()

    def reload(self):
        """Read the shipped feed file and the changelog again."""

        if self.section is not None:
            self.section.controller.reload()

    def push_from_file(self):
        """Push a post or feed chosen in a file dialog."""
        path = file_dialog(
            parent=self.window(),
            default_path=str(FEED_PATH.parent),
            wildcard=JSON_WILDCARD,
        )

        if path and self.section is not None:
            self.section.controller.push_file(path)
            self.section.expanded = True

    def push_sample(self):
        """Push the demo's placeholder post, under a new id each time, so
        each push is a new post and alerts."""

        if self.section is None:
            return

        self._pushed += 1

        self.section.controller.push(
            {**SAMPLE_PUSH_POST, "id": f"{SAMPLE_PUSH_POST['id']}-{self._pushed}"}
        )
