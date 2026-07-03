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

from pyface.ui.qt.tasks.dock_pane import AREA_MAP

from logger.logger_service import get_logger

logger = get_logger(__name__)


def add_dock_pane_live(window, task, factory, area=None):
    """Create ``factory`` and dock it onto the live ``window`` at runtime.

    Mirrors ``TaskWindowBackend._layout_state``: create the QDockWidget,
    ``addDockWidget`` it onto the QMainWindow (``window.control``), show it,
    and register it in both the active ``TaskState`` and the window so
    ``window.get_dock_pane(id)`` and the View-menu toggle group see it.

    ``area`` overrides the pane's own ``dock_area`` ('left'/'right'/'top'/
    'bottom'); pass None to honour the pane default. Returns the pane.
    """
    state = window._active_state
    if state is None:
        logger.warning("add_dock_pane_live: window has no active task state; cannot add pane")
        return None

    main_window = window.control
    pane = factory(task=task)
    pane.task = task
    pane.create(main_window)

    main_window.addDockWidget(AREA_MAP[area or pane.dock_area], pane.control)
    pane.visible = True
    pane.control.show()

    state.dock_panes = state.dock_panes + [pane]
    window.dock_panes = state.dock_panes

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
        window.menu_bar_manager = new_manager

    if old_manager is not None and old_manager is not new_manager:
        try:
            old_manager.destroy()
        except Exception:
            logger.exception(
                "rebuild_menu_bar_live: failed to destroy old menu bar manager"
            )
    logger.debug("rebuild_menu_bar_live: menu bar rebuilt")
