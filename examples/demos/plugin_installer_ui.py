"""Standalone plugin installer — the Browse Plugins window, run on its own.

Wires the REAL plugin-management MVC (``BrowsePluginsModel`` +
``BrowsePluginsHandler`` + ``browse_view``) into a tiny Qt app so the install
flow can be exercised without launching the whole MicroDrop application:

    pixi run python examples/demos/plugin_installer_ui.py

On open it runs ``pixi search`` against the plugin channel (cached to app-data),
lists the packages, shows the selected package's details as HTML (the URL opens
in your browser), and Install runs ``pixi add`` for real. There is no Envisage
task here, so ``task=None``; after a successful install ``confirm_and_relaunch``
degrades to "takes effect next launch" instead of relaunching.
"""
import sys

from pyface.qt.QtWidgets import QApplication

from microdrop_style.helpers import style_app
from plugin_management.browse_model import BrowsePluginsModel
from plugin_management.browse_view import browse_view
from plugin_management.browse_controller import BrowsePluginsHandler


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)

    model = BrowsePluginsModel()
    # No Envisage Task in standalone mode; the controller tolerates task=None
    # (relaunch-after-install degrades to a "next launch" notice).
    handler = BrowsePluginsHandler(task=None)

    # browse_view is kind="livemodal", so edit_traits runs its own modal loop
    # and blocks until the window is closed — no separate app.exec() needed.
    model.edit_traits(view=browse_view, handler=handler)


if __name__ == "__main__":
    main()
