# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A standalone prototype of the protocol pre-flight check: a readiness pill
in the status bar beside the mode/step label, and a card of checks opening
upward from it, from the real ``pluggable_protocol_tree.preflight``
package; everything here is the harness. Mock state only: no Redis, no
hardware, no plugins. Run from ``src/``:

    pixi run python -m examples.demos.preflight_check.run_preflight_check_demo

``--theme light`` or ``dark`` forces a theme; ``--open`` opens the popover
once the first checks have run; ``--scenario NAME`` starts on a scenario.
"""

# Standard library imports.
import argparse
import signal
import sys

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop style imports.
from microdrop_style.helpers import style_app
from microdrop_style.palettes import dark_palette

# Local imports.
from .demo_window import PreflightDemoWindow
from .mock_context import SCENARIOS

#: Time after start-up before ``--open`` opens the popover, ms.
OPEN_DELAY_MS = 1200


def main():
    """Parse the flags, build the window and run until it closes."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--theme", choices=["light", "dark", "system"])
    parser.add_argument("--open", action="store_true", help="open the popover")
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="Mixed")
    args = parser.parse_args()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    style_app(app)

    if args.theme == "dark":
        app.setPalette(dark_palette())

    elif args.theme == "light":
        app.setPalette(app.style().standardPalette())

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    window = PreflightDemoWindow()
    window.controls.scenario = args.scenario
    window.show()

    if args.open:
        QtCore.QTimer.singleShot(OPEN_DELAY_MS, window.open_popover)

    app.exec()


if __name__ == "__main__":
    main()
