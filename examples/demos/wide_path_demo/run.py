# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Run the wide-path testbed.

From ``microdrop-py/``::

    pixi run python -m examples.demos.wide_path_demo.run [device.svg]

Opens the bundled 2x3 device with one empty path selected. Click (or drag
across) neighbouring electrodes to draw its route; revisiting electrodes
makes loops and knots, as in the device viewer (Undo last, or Esc to clear).
Set left/right lanes and trail/overlay, and step through the phases with the
ticker or the timeline. The algorithm is ``wide_path_geometry.slug_phases``,
covered by ``tests/test_slug_phases.py`` against the corner-turning game
answers.
"""

# Standard library imports.
import sys

# Enthought library imports.
from pyface.qt.QtWidgets import QApplication

# Microdrop style imports.
from microdrop_style.helpers import style_app

# Local imports.
from .consts import DEFAULT_DEVICE_SVG_PATH
from .controller import WidePathDemoController
from .models import WidePathDemoModel
from .view import WidePathDemoView


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)

    model = WidePathDemoModel()
    controller = WidePathDemoController(model=model)
    svg_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DEVICE_SVG_PATH
    controller.load_device_svg(svg_path)
    model.add_path("path 1")

    model.configure_traits(view=WidePathDemoView)


if __name__ == "__main__":
    main()
