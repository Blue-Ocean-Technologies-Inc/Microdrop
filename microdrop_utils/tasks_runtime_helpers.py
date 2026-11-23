# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Runtime add/remove of Pyface Tasks dock panes on a live window.

Pyface Tasks gathers dock panes once, at ``TaskWindow.add_task`` time, and
provides no public API to add or remove a pane after the window is shown — it
only supports toggling the visibility of panes created at startup. These
helpers drive the underlying Qt directly, replicating the exact sequences the
framework uses internally (``_layout_state`` for add, ``hide_task`` for
remove), so a plugin loaded at runtime can mount/unmount its dock pane.

Qt is imported here on purpose: this is a view-layer helper, not a model or
service. The pane factory is any ``DockPane`` subclass/callable taking
``task=...`` (the same shape envisage ``TaskExtension.dock_pane_factories``
use).
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from pyface.ui.qt.tasks.dock_pane import AREA_MAP

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def add_dock_pane_live(window, task, factory, area=None):
    """Create ``factory`` and dock it onto the live ``window`` at runtime.

    Mirrors ``TaskWindowBackend._layout_state``: create the QDockWidget,
    ``addDockWidget`` it onto the QMainWindow (``window.control``), and
    register it in both the active ``TaskState`` and the window so
    ``window.get_dock_pane(id)`` and the View-menu toggle group see it. The
    pane is NOT force-shown — it keeps its own ``visible`` state / the
    restored saved layout — so a plugin group contributing several panes
    doesn't crowd the window (which was clipping the status bar, #520).

    ``area`` overrides the pane's own ``dock_area`` ('left'/'right'/'top'/
    'bottom'); pass None to honour the pane default. Returns the pane.

    A pane already mounted under the same id (a placeholder standing in
    while its plugin loads) is replaced in place: the new pane takes its
    position, size, tab, floating state and visibility, and ``area`` is
    ignored.
    """
    state = window._active_state
    if state is None:
        logger.warning(
            "add_dock_pane_live: window has no active task state; cannot add pane"
        )
        return None

    main_window = window.control
    pane = factory(task=task)
    pane.task = task
    pane.create(main_window)

    placeholder = state.get_dock_pane(pane.id)

    if placeholder is None:
        main_window.addDockWidget(AREA_MAP[area or pane.dock_area], pane.control)
        state.dock_panes = state.dock_panes + [pane]

    else:
        _take_dock_place(main_window, placeholder, pane)
        state.dock_panes = [
            pane if dock_pane is placeholder else dock_pane
            for dock_pane in state.dock_panes
        ]

    window.dock_panes = state.dock_panes

    # Only once no pane list holds it: pyface's focus tracking walks
    # window.dock_panes and fails on a pane without its control.
    if placeholder is not None:
        placeholder.destroy()

    # Let the pane finish any wiring that needs the live window (e.g. the
    # peripheral pane installs its status-bar icon here — its
    # task:window:status_bar_manager observer never fires on a hot-mount
    # because the status bar already exists).
    on_live_mounted = getattr(pane, "on_live_mounted", None)
    if callable(on_live_mounted):
        try:
            on_live_mounted()
        except Exception:
            logger.exception(
                f"add_dock_pane_live: on_live_mounted hook failed for '{pane.id}'"
            )

    logger.info(f"add_dock_pane_live: mounted dock pane '{pane.id}'")
    return pane


def _take_dock_place(main_window, old_pane, new_pane):
    """Put ``new_pane``'s dock widget exactly where ``old_pane``'s was.

    Takes the old dock widget off the window; the caller destroys the pane.

    Both dock widgets carry the same object name (pyface names them
    ``task_id:pane_id``), which is what ``QMainWindow.saveState`` records
    each dock widget's area, size, tab group, floating geometry and
    visibility under. Saving the state, swapping the widgets and restoring
    it therefore gives the new widget the old one's whole placement, and
    leaves every other dock widget where it was.
    """
    window_state = main_window.saveState()
    area = main_window.dockWidgetArea(old_pane.control)

    # Only one widget may answer to the name while the state is restored.
    old_pane.control.setObjectName("")
    old_pane.control.hide()
    main_window.removeDockWidget(old_pane.control)

    if area == QtCore.Qt.DockWidgetArea.NoDockWidgetArea:
        area = AREA_MAP[new_pane.dock_area]

    main_window.addDockWidget(area, new_pane.control)
    main_window.restoreState(window_state)


def remove_dock_pane_live(window, pane_id):
    """Hide, undock and destroy the live dock pane with ``pane_id``.

    Mirrors ``TaskWindowBackend.hide_task``: ``hide()`` then
    ``removeDockWidget`` (order matters — the framework comments warn the
    layout is wrong if switched), then ``pane.destroy()`` (which runs any
    pane-specific teardown), then drop it from the state/window lists.
    No-op (returns None) if the pane isn't currently mounted.
    """
    state = window._active_state
    if state is None:
        return None

    pane = state.get_dock_pane(pane_id)
    if pane is None:
        logger.debug(f"remove_dock_pane_live: no live dock pane '{pane_id}'")
        return None

    pane.control.hide()
    window.control.removeDockWidget(pane.control)
    pane.destroy()

    state.dock_panes = [p for p in state.dock_panes if p is not pane]
    window.dock_panes = state.dock_panes
    logger.info(f"remove_dock_pane_live: removed dock pane '{pane_id}'")
    return pane


def restore_saved_task_layout(window, application):
    """Re-apply the dock-pane layout envisage saved at the last exit.

    Envisage restores the saved layout exactly once, at window creation
    (``TasksApplication._create_windows``). A dock pane whose plugin is
    hot-loaded afterwards (the plugin-group launch restore) does not exist at
    that point, so pyface drops its saved ``PaneItem`` ("Cannot retrieve dock
    widget for pane") and the pane is later mounted at its default dock area.
    Calling this after the hot-loaded panes are mounted re-applies the saved
    layout against the now-complete pane set. Saved panes that no longer exist
    are still skipped by pyface with a warning; live panes without a saved
    placement fall back to their default dock area.

    Returns True if a saved layout was found and applied.
    """
    if getattr(application, "always_use_default_layout", False):
        logger.debug("restore_saved_task_layout: skipped (always_use_default_layout)")
        return False

    # The envisage TasksApplicationState loaded from the application_memento
    # pickle — kept on the application for its lifetime, no public accessor.
    saved_application_state = getattr(application, "_state", None)
    task = window.active_task
    if saved_application_state is None or task is None:
        return False

    saved_task_layout = saved_application_state.get_task_layout(task.id)
    if saved_task_layout is None:
        logger.debug(f"restore_saved_task_layout: no saved layout for task '{task.id}'")
        return False

    # Clone so the live window's subsequent layout mutations cannot corrupt
    # the state object that gets pickled back at exit.
    window._window_backend.set_layout(saved_task_layout.clone_traits())
    logger.info(
        f"restore_saved_task_layout: re-applied saved layout for task '{task.id}'"
    )
    return True


def rebuild_menu_bar_live(window, task, application):
    """Rebuild a live ``TaskWindow``'s menu bar from the CURRENT started
    plugins' TaskExtension actions.

    Pyface gathers SchemaAdditions into ``task.extra_actions`` once at window
    creation (``TaskWindow.add_task``) and never updates them when a plugin
    starts/stops, so a hot-loaded plugin's menu contributions never appear (and
    an unloaded plugin's never disappear). We recompute ``extra_actions`` from
    the live ``application.task_extensions`` extension point (which reflects
    only started plugins), rebuild the menu-bar manager, and assign it so
    Pyface's Qt observer (``_menu_bar_manager_updated`` -> ``setMenuBar``) swaps
    it onto the QMainWindow. Static items in ``task.menu_bar`` are preserved;
    only plugin-contributed additions change.
    """
    task.extra_actions = [
        addition
        for extension in application.task_extensions
        if (not extension.task_id) or extension.task_id == task.id
        for addition in extension.actions
    ]

    builder = window.action_manager_builder_factory(task=task)
    new_manager = builder.create_menu_bar_manager()

    state = window._get_state(task)
    if state is None:
        logger.warning("rebuild_menu_bar_live: no task state; cannot rebuild menu bar")
        return

    old_manager = state.menu_bar_manager
    state.menu_bar_manager = new_manager

    # If this task is the active one, push to the window trait — that triggers
    # Pyface's _menu_bar_manager_updated, which calls setMenuBar on the live
    # control (QMainWindow replaces and owns the old menu bar).
    if window._active_state is state:
        _swap_menu_bar(window, new_manager)

    if old_manager is not None and old_manager is not new_manager:
        try:
            old_manager.destroy()
        except Exception:
            logger.exception(
                "rebuild_menu_bar_live: failed to destroy old menu bar manager"
            )
    logger.debug("rebuild_menu_bar_live: menu bar rebuilt")


def _swap_menu_bar(window, menu_bar_manager):
    """Put a new menu bar on the live window without a frame lacking one.

    Qt shows a menu bar set on a visible window only on the next event-loop
    turn; a paint before then lays the window out without it, and every
    dock jumps up by the bar's height and back. Showing the new bar at once,
    with painting held for the swap, keeps the bar on screen throughout.
    """
    main_window = window.control
    main_window.setUpdatesEnabled(False)

    try:
        window.menu_bar_manager = menu_bar_manager
        main_window.menuBar().show()

    finally:
        main_window.setUpdatesEnabled(True)


def describe_dock_widgets(main_window):
    """Describe every dock widget's geometry, for a window pyface refused to save.

    Runs during application shutdown, so it must never raise itself; any
    failure while introspecting the window is returned as text instead.
    """
    try:
        lines = []

        for widget in main_window.findChildren(QtWidgets.QDockWidget):
            geometry = widget.geometry()
            tabified_titles = [
                tabbed.windowTitle()
                for tabbed in main_window.tabifiedDockWidgets(widget)
            ]
            lines.append(
                f"{widget.windowTitle()!r} visible={widget.isVisible()} "
                f"area={main_window.dockWidgetArea(widget)} "
                f"geometry={geometry.x()},{geometry.y()} "
                f"{geometry.width()}x{geometry.height()} "
                f"floating={widget.isFloating()} tabified_with={tabified_titles}"
            )

        return "\n".join(lines)
    except Exception as error:
        return f"Could not describe dock widgets: {error}"
