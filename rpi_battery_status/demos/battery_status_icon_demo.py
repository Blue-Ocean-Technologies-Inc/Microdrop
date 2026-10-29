# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Eyeball the battery icon in a bare status bar, without the app.

Click the icon to open the details panel; it keeps updating while open.
By default cycles through synthetic snapshots, one per second, covering
every glyph and colour; ``--file PATH`` instead polls a real status.json,
e.g. ``/run/user/1000/rpi-battery-monitor/status.json`` on the Pi. Run from
``src/``:

    pixi run python -m rpi_battery_status.demos.battery_status_icon_demo [--file PATH]
"""

# Standard library imports.
import argparse
import itertools
import time
from pathlib import Path

# Enthought library imports.
from pyface.api import GUI
from pyface.qt import QtWidgets
from pyface.timer.api import Timer

# Microdrop style imports.
from microdrop_style.helpers import style_app

# Local imports.
from ..controllers.battery_status_controller import BatteryStatusController
from ..views.battery_details_view import show_battery_details
from ..views.battery_status_view import build_status_bar_icon

#: Pack fields every synthetic snapshot carries, for the details panel.
SYNTHETIC_PACK = {"cells": 6, "chemistry": "li-ion", "soc_source": "coulomb"}

#: Every fill glyph discharging then charging, then the special states
#: (alert, no pack, unknown level, daemon unavailable), shown in this order.
SYNTHETIC_SNAPSHOTS = [
    *(
        {
            "soc": soc,
            "voltage": 20 + soc / 20,
            "current": 1.2,
            "power": 1.2 * (20 + soc / 20),
            "state": "Discharging",
            "remaining_ah": soc / 2,
            "time_to_empty_s": soc * 150,
        }
        for soc in (100, 85, 70, 55, 40, 25, 12, 3)
    ),
    *(
        {
            "soc": soc,
            "voltage": 22 + soc / 25,
            "current": -5.9,
            "power": -5.9 * (22 + soc / 25),
            "state": "Charging",
            "remaining_ah": soc / 2,
            "charging": True,
            "time_to_full_s": (100 - soc) * 600,
        }
        for soc in (10, 30, 50, 65, 80, 92, 100)
    ),
    {"soc": 6.0, "voltage": 20.9, "alert": True},
    {"soc": 50.0, "voltage": 26.1, "battery_absent": True},
    {"soc": None, "voltage": 24.0},
    None,
]


def main():
    """Show the icon in a small window's status bar until it is closed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, help="poll this status.json")
    args = parser.parse_args()

    gui = GUI()

    # Registers the icon font the glyph ligatures need, as the app does.
    style_app(QtWidgets.QApplication.instance())

    controller = BatteryStatusController()
    model = controller.model

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Battery status icon demo")
    window.resize(480, 120)

    details_ui = None

    def show_details():
        nonlocal details_ui
        details_ui = show_battery_details(model, icon, details_ui)

    icon, ui = build_status_bar_icon(model, on_click=show_details)
    window.statusBar().addPermanentWidget(icon)
    window.show()

    if args.file is not None:
        controller.path = args.file
        controller.start()
    else:
        snapshots = itertools.cycle(SYNTHETIC_SNAPSHOTS)

        def show_next_snapshot():
            snapshot = next(snapshots)
            now = time.time()

            if snapshot is None:
                model.mark_unavailable()
            else:
                model.apply_snapshot(
                    {**SYNTHETIC_PACK, **snapshot, "timestamp": now}, now
                )

            window.statusBar().showMessage(f"{model.level}: {model.tooltip}")

        # Held so the running timer is not garbage collected.
        timer = Timer(1000, show_next_snapshot)  # noqa: F841

    gui.start_event_loop()


if __name__ == "__main__":
    main()
