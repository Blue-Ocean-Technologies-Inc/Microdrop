# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Eyeball the plugin load-status indicator and panel, without the app.

Fake plugins start one per step in a bare status bar: the indicator pulses
while they load, then shows a red X because one of them fails. Click it to
open the panel. Run from ``src/``:

    pixi run python -m plugin_management.demos.plugin_load_status_demo
"""

# Standard library imports.
from types import SimpleNamespace

# Enthought library imports.
from pyface.api import GUI
from pyface.qt import QtWidgets
from pyface.timer.api import Timer

# Microdrop style imports.
from microdrop_style.helpers import style_app

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import PluginLoadStatus

# Local imports.
from ..load_status_controller import PluginLoadStatusController
from ..load_status_model import PluginLoadStatusPanelModel
from ..load_status_view import PluginLoadStatusIndicator

#: The fake plugins, in load order; the one named "Broken" fails to start.
FAKE_PLUGINS = [
    SimpleNamespace(id="envisage.core", name="Core"),
    SimpleNamespace(id="message_router.plugin", name="Message Router Plugin"),
    SimpleNamespace(id="device_viewer.plugin", name="Device Viewer Plugin"),
    SimpleNamespace(id="broken_demo.plugin", name="Broken Demo Plugin"),
    SimpleNamespace(id="image_viewer.plugin", name="Image Viewer Plugin"),
]

#: Ms between fake plugin starts.
STEP_MS = 800


def _start_fake_plugin(plugin):
    """Stand in for a plugin's start(): the broken one raises."""
    if plugin.id.startswith("broken"):
        raise RuntimeError("could not open the demo device")


def make_fake_status():
    """Return a status with every fake plugin pending."""
    status = PluginLoadStatus()

    for plugin in FAKE_PLUGINS:
        status.mark_pending(plugin.id, plugin.name, plugin.id == "envisage.core")

    return status


def start_next_fake_plugin(status):
    """Start the first pending fake plugin; return False once none is left."""
    for plugin in FAKE_PLUGINS:
        if status.get_record(plugin.id).state == "pending":
            try:
                with status.recording(plugin):
                    _start_fake_plugin(plugin)

            except RuntimeError:
                pass  # recorded as failed, as the plugin manager would

            return True

    return False


def main():
    """Show the indicator in a small window's status bar until it closes."""
    gui = GUI()

    # Registers the icon font the glyphs need, as the app does.
    style_app(QtWidgets.QApplication.instance())

    status = make_fake_status()
    indicator = PluginLoadStatusIndicator(status=status)
    controller = PluginLoadStatusController(
        model=PluginLoadStatusPanelModel(status=status)
    )
    indicator.widget.clicked.connect(
        lambda: controller.show_panel(indicator.widget.window())
    )

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Plugin load-status demo")
    window.resize(480, 120)
    window.statusBar().addPermanentWidget(indicator.widget)
    window.show()

    def step():
        if not start_next_fake_plugin(status):
            timer.Stop()

        window.statusBar().showMessage(status.summary)

    timer = Timer(STEP_MS, step)

    gui.start_event_loop()


if __name__ == "__main__":
    main()
