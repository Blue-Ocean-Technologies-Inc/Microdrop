# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Run the minimal electrode zones demo.

From ``microdrop-py/``::

    pixi run python -m examples.demos.zones_demo.run_zones_demo [device.svg]

Load a device SVG (defaults to the bundled 2x3 device), pick a zone type in
the sidebar's zones tree, and switch tools in the Pan / Draw zones / Select
radio:

- **Pan** scrolls/zooms the device and drops any pending selection.
- **Draw zones** rubber-bands (or click-toggles) electrodes into a pending
  selection; the floating check/delete/dismiss strip and the sidebar's
  Commit/Clear buttons act on it.
- **Select** picks existing regions (click, ctrl+click to multi-select, or
  rubber-band); the floating edit/delete/hide strip and the sidebar's
  Edit/Merge buttons act on the selection, and dragging a region snaps
  it to a new electrode block.

Right-click a region for its context menu: Edit region, Change type, Delete
region. Undo/redo cover every zone mutation.

The feature has been ported into device_viewer (see
docs/superpowers/specs/2026-08-26-electrode-zones-design.md); this demo
remains the standalone interaction reference.
"""

# Standard library imports.
import sys

# Enthought library imports.
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from device_viewer.consts import DEFAULT_ZONE_TYPES

# Microdrop style imports.
from microdrop_style.helpers import style_app

# Local imports.
from .consts import DEFAULT_DEVICE_SVG_PATH
from .controller import ZonesDemoController
from .models import ZonesDemoModel
from .view import ZonesDemoView


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)

    model = ZonesDemoModel()
    for name, color in DEFAULT_ZONE_TYPES:
        model.manager.add_zone_type(name, color)
    model.manager.selected_zone_type = model.manager.zone_types[0]

    controller = ZonesDemoController(model=model)
    svg_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DEVICE_SVG_PATH
    controller.load_device_svg(svg_path)

    # configure_traits starts the Qt event loop.
    model.configure_traits(view=ZonesDemoView)


if __name__ == "__main__":
    main()
