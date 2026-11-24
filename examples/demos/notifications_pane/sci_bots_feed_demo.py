# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications demo's Sci-Bots Feed: its section and toolbar actions.

Reload re-reads ``sci_bots_feed.json`` and CHANGELOG.md; the push actions
send a post or a document through the controller's push path, as a topic
would later; Feed creator… opens the creator, able to send to this feed.
Problems show in the feed's status line, not in dialogs.
"""

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import file_dialog

# Local imports.
from .feed_creator import open_feed_creator
from .sci_bots_feed_controller import SciBotsFeedController
from .sci_bots_feed_releases import ChangelogFeedSource
from .sci_bots_feed_section import SciBotsFeedSection
from .sci_bots_feed_sources import DEFAULT_FEED_PATH, demo_feed_sources

#: What Push sample post sends: a placeholder with rich text.
SAMPLE_PUSH_POST = {
    "id": "demo-sample-push",
    "title": "PLACEHOLDER pushed post — rich text sample",
    "date": "2026-11-23",
    "kind": "announcement",
    "source": "Demo push",
    "summary": "Sample content pushed from the demo toolbar.",
    "summary_html": (
        "<p><b>Sample content</b> pushed from the demo toolbar, with a "
        '<a href="https://www.linkedin.com/company/sci-bots-inc./posts/">link</a>'
        " and a list:</p><ul><li>first point</li><li><i>second</i> point</li>"
        "</ul>"
    ),
    "url": "https://www.linkedin.com/company/sci-bots-inc./posts/",
}

#: The file dialog's filter for feed and post JSON files.
JSON_WILDCARD = "JSON files (*.json)"


def create_feed_section():
    """The feed section, expanded, loaded from the demo's feed file and the
    recent releases in CHANGELOG.md."""
    controller = SciBotsFeedController(
        sources=[*demo_feed_sources(), ChangelogFeedSource()]
    )
    controller.reload()

    # Open, as the demo's subject; capped, so the notifications stay in view.
    return SciBotsFeedSection(controller=controller, expanded=True)


def add_feed_actions(toolbar, section, window_control):
    """The feed's demo actions on ``toolbar``."""
    controller = section.controller
    # Held: an open creator window must outlive this function.
    creators = []

    def open_creator():
        creators[:] = [ui for ui in creators if ui.control is not None]
        creators.append(
            open_feed_creator(
                str(DEFAULT_FEED_PATH), feed_controller=controller, parent=None
            )
        )

    def push_from_file():
        path = file_dialog(
            parent=window_control,
            default_path=str(DEFAULT_FEED_PATH.parent),
            wildcard=JSON_WILDCARD,
        )

        if path:
            controller.push_file(path)
            section.expanded = True

    def push_sample():
        controller.push(SAMPLE_PUSH_POST)
        section.expanded = True

    toolbar.addAction("Reload feed", controller.reload)
    toolbar.addAction("Push post from JSON…", push_from_file)
    toolbar.addAction("Push sample post", push_sample)
    toolbar.addAction("Feed creator…", open_creator)
