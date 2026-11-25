# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Bring a dock pane forward to show something in it, e.g. a notification's
Show button opening a capture in its viewer.

A pane already on screen is raised where it is: docked, behind another tab
(its tab is selected) or floating; it is never undocked. A closed pane pops
out floating, centred over the main window. "On screen" is read from the dock
widget: a closed pane's widget is hidden, while one behind a tab is only moved
out of sight, and pyface's ``visible`` stays True for it.

A view-layer helper: it imports Qt through ``pyface.qt``.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Local imports.
from .lazy_dock_pane import LazyContentDockPane

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Raise the pane where it is: it is on screen, docked or floating.
RAISE = "raise"

#: Show a closed pane floating over the main window.
POP_OUT = "pop_out"

#: Show a closed pane docked where it was: it cannot float.
SHOW_DOCKED = "show_docked"

#: A popped-out pane's size, as a fraction of the main window's.
POP_OUT_FRACTION = 0.6

#: The smallest popped-out pane, in pixels.
POP_OUT_MINIMUM_WIDTH = 640
POP_OUT_MINIMUM_HEIGHT = 480


def presentation_for(closed, floatable):
    """How to bring a dock widget forward: RAISE it unless ``closed``, else
    POP_OUT, or SHOW_DOCKED when it cannot float."""

    if not closed:
        return RAISE

    return POP_OUT if floatable else SHOW_DOCKED


def live_dock_pane(application, pane_id):
    """The dock pane ``pane_id`` of the application's active window (its
    first window when none is active), or None."""
    window = getattr(application, "active_window", None)

    if window is None:
        windows = getattr(application, "windows", None) or []
        window = windows[0] if windows else None

    if window is None:
        return None

    return window.get_dock_pane(pane_id)


def present_dock_pane(pane, then=None):
    """Bring ``pane`` forward (see the module docstring), then call
    ``then()`` once its contents exist: at once for a pane built with its
    window, after its build for a ``LazyContentDockPane``, which is built
    now. ``then`` is not called if that build fails; the pane shows why."""
    dock = pane.control
    floatable = bool(
        dock.features() & QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
    )
    presentation = presentation_for(dock.isHidden(), floatable)

    if presentation == POP_OUT:
        dock.setFloating(True)
        dock.setGeometry(_pop_out_geometry(dock, pane.task.window.control))

    if presentation != RAISE:
        dock.show()

    # On a docked pane behind a tab, raise_() selects its tab.
    dock.raise_()
    dock.activateWindow()
    logger.debug(f"Brought {pane.id} forward: {presentation}")

    if then is None:
        return

    if isinstance(pane, LazyContentDockPane):
        pane.ensure_built()
        pane.when_content_built(lambda _contents: then())

    else:
        then()


def _pop_out_geometry(dock, main_window):
    """A floating pane's geometry: a share of ``main_window``'s size, no
    smaller than the pane allows, centred over the window."""
    window_geometry = main_window.geometry()
    width = max(
        int(window_geometry.width() * POP_OUT_FRACTION),
        POP_OUT_MINIMUM_WIDTH,
        dock.minimumWidth(),
    )
    height = max(
        int(window_geometry.height() * POP_OUT_FRACTION),
        POP_OUT_MINIMUM_HEIGHT,
        dock.minimumHeight(),
    )

    geometry = QtCore.QRect(0, 0, width, height)
    geometry.moveCenter(window_geometry.center())

    return geometry
