# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Standalone demo of the MicroDrop Updates dialog on this source checkout (no
application, no Redis). Run from the repo root:

    python -m examples.demos.app_updates_dialog_demo [--repo <checkout>]

The policy is kept in in-memory preferences, so changing it saves nothing.
The buttons are real: "Check for updates" fetches tags, and a switch checks
the checkout out and closes the dialog — so to try a switch, point --repo at
a throwaway clone detached at a release tag (``git clone <this repo> <dir>``,
then ``git -C <dir> checkout --detach v1.45.0``)."""

# Standard library imports.
import argparse
import sys

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from app_updates.controller import UpdatesController
from app_updates.model import UpdatesModel
from app_updates.preferences import AppUpdatesPreferences
from app_updates.view import updates_view

# Microdrop style imports.
from microdrop_style.helpers import style_app

# Microdrop utils imports.
from microdrop_utils.source_update_startup import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description="Open the MicroDrop Updates dialog.")
    parser.add_argument(
        "--repo",
        default=str(PROJECT_ROOT),
        help="the source checkout to show and switch (default: this one)",
    )
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)

    style_app(app)

    model = UpdatesModel(
        repo_root=args.repo,
        preferences=AppUpdatesPreferences(preferences=Preferences()),
    )
    model.refresh()

    model.edit_traits(view=updates_view, handler=UpdatesController(model=model))


if __name__ == "__main__":
    main()
