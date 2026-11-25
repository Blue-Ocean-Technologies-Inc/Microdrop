# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The news feed creator: write the feed file, with a live preview.

For staff who own the feed's content: fill in a form per post, see the
card exactly as the News section shows it, fix what Checks lists, and save.
It opens on the feed file shipped with MicroDrop,
``news/resources/feed.json``, unless given another. No Redis, nothing
published. Run from ``src/``::

    pixi run python -m news.feed_creator [FEED.json] [--theme light|dark]

The dev Demo menu opens it non-modally with "Feed creator…", adding Send
to the News section.
"""

# Standard library imports.
import argparse

# Enthought library imports.
from pyface.qt import QtWidgets

# Microdrop style imports.
from microdrop_style.helpers import apply_color_scheme, style_app

# Local imports.
from ..consts import FEED_PATH
from .controller import FeedCreatorController
from .model import FeedCreatorModel
from .view import FeedCreatorView


def open_feed_creator(path=None, feed_controller=None, parent=None, kind="live"):
    """Open the creator on the feed file at ``path`` (a new file if None);
    with ``feed_controller`` it can send to that feed. Returns the UI."""
    controller = FeedCreatorController(
        model=FeedCreatorModel(can_send=feed_controller is not None),
        feed_controller=feed_controller,
    )

    if path:
        controller.open_file(path)

    return controller.edit_traits(view=FeedCreatorView, kind=kind, parent=parent)


def main():
    """Show the creator until it is closed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "path", nargs="?", default=str(FEED_PATH), help="a feed file to open"
    )
    parser.add_argument(
        "--theme", choices=["light", "dark", "system"], default="system"
    )
    args = parser.parse_args()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    style_app(app)
    apply_color_scheme(args.theme)

    open_feed_creator(args.path)
    app.exec()
