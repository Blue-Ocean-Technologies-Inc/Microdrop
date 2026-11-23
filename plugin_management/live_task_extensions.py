# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Reactively mount/unmount dock panes and rebuild the menu bar when plugins
contribute/withdraw TASK_EXTENSIONS at runtime.

Pyface Tasks gathers a task's dock panes + menu bar once at window creation, so
a plugin loaded afterwards needs its panes mounted and the menu rebuilt on the
live window (see ``microdrop_utils/tasks_runtime_helpers``). This controller
turns that from imperative ``PluginGroupManager`` calls into a reactive,
coalesced reconcile driven by the TASK_EXTENSIONS extension point — so *any*
runtime-loaded plugin's panes/menu appear automatically.

This is a Qt-free ``HasTraits`` controller. The TASK_EXTENSIONS delta fires
synchronously inside ``add_plugin``/``remove_plugin`` (on the GUI thread), so we
**defer** the reconcile to the next event-loop turn with ``pyface.api.GUI``
(``invoke_later`` — toolkit-agnostic, not raw Qt). Deferral has two effects:
it runs the reconcile *after* the manager's synchronous add+start loop (so panes
are created once their plugins are started), and the ``_scheduled`` guard
coalesces a whole burst of deltas into a single reconcile + a single menu
rebuild.

(Note: ``@observe(dispatch="ui")`` does NOT help here — traits' ui-dispatch runs
the handler inline when the change is already on the main thread, so it would
neither defer nor coalesce. ``GUI.invoke_later`` is the deferral primitive.)
"""

# Enthought library imports.
from pyface.api import GUI
from traits.api import Any, Bool, Dict, HasTraits, List, Property, observe
from traits.observation.api import trait

# Microdrop utils imports.
from microdrop_utils.tasks_runtime_helpers import (
    add_dock_pane_live,
    rebuild_menu_bar_live,
    remove_dock_pane_live,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class LiveTaskExtensionsController(HasTraits):
    """Mount/unmount dock panes + rebuild the menu bar for TaskExtensions added
    or removed at runtime, coalesced and deferred to the GUI event loop."""

    #: The TasksApplication — read for active_window/active_task at reconcile.
    application = Any()

    #: TaskExtensions accumulated since the last reconcile.
    _pending_added = List()
    _pending_removed = List()

    #: factory class -> the id of the pane instance we mounted for it, so we can
    #: unmount by id later (a DockPane subclass's ``id`` trait value isn't
    #: reliably readable off the class object).
    _pane_id_by_factory = Dict()

    #: True once a reconcile is queued on the UI loop — coalesces a burst of
    #: TASK_EXTENSIONS changes into one reconcile.
    _scheduled = Bool(False)

    has_mounted_panes = Property(Bool)

    def _get_has_mounted_panes(self):
        """True while at least one dock pane this controller hot-mounted is
        still mounted (entries are dropped again on unmount)."""
        return bool(self._pane_id_by_factory)

    #: True while TASK_EXTENSIONS changes wait for their reconcile, e.g.
    #: because no window shows its task yet.
    has_pending_changes = Property(Bool)

    def _get_has_pending_changes(self):
        return bool(self._pending_added or self._pending_removed)

    def on_changed(self, added, removed):
        """Record a TASK_EXTENSIONS delta and schedule one deferred reconcile.

        An extension withdrawn before the reconcile that would mount it (a
        plugin rolled back right after being added) cancels out instead of
        being mounted for a plugin that is gone."""
        for extension in removed:
            if extension in self._pending_added:
                self._pending_added.remove(extension)
            else:
                self._pending_removed.append(extension)

        self._pending_added.extend(added)
        self._schedule_reconcile()

    def mounted_pane_ids(self, extensions):
        """Return the ids of the dock panes mounted for ``extensions``."""
        return [
            self._pane_id_by_factory[factory]
            for extension in extensions
            for factory in getattr(extension, "dock_pane_factories", []) or []
            if factory in self._pane_id_by_factory
        ]

    def unmount_pane(self, pane_id):
        """Take the dock pane ``pane_id`` off the active window, if shown."""
        window = getattr(self.application, "active_window", None)

        if window is None:
            return

        try:
            remove_dock_pane_live(window, pane_id)

        except Exception:
            logger.exception(f"unmount of '{pane_id}' failed")

    # --- internals ---------------------------------------------------

    def _schedule_reconcile(self):
        if not self._scheduled:
            self._scheduled = True
            GUI.invoke_later(self._reconcile)

    @observe(
        trait("application", notify=False)
        .trait("active_window", optional=True)
        .trait("active_task", optional=True)
    )
    def _reconcile_once_a_task_shows(self, event):
        """Apply the changes kept while no window showed its task."""
        if self.has_pending_changes:
            self._schedule_reconcile()

    def _reconcile(self):
        self._scheduled = False

        application = self.application
        window = getattr(application, "active_window", None)
        task = getattr(window, "active_task", None)

        # Keep the changes until a window shows its task: dropping them here
        # would lose the panes and menus of every plugin loaded before then.
        if task is None:
            return

        added, removed = self._pending_added, self._pending_removed
        self._pending_added, self._pending_removed = [], []

        # Removed first: drop panes whose plugin is going away before mounting
        # new ones.
        for ext in removed:
            if not self._matches(ext, task):
                continue
            for factory in getattr(ext, "dock_pane_factories", []) or []:
                pane_id = self._pane_id_by_factory.pop(factory, None)
                if pane_id is None:
                    continue
                try:
                    remove_dock_pane_live(window, pane_id)
                except Exception:
                    logger.exception(f"reactive unmount of '{pane_id}' failed")

        for ext in added:
            if not self._matches(ext, task):
                continue
            for factory in getattr(ext, "dock_pane_factories", []) or []:
                try:
                    pane = add_dock_pane_live(window, task, factory)
                except Exception:
                    logger.exception("reactive mount of a dock pane failed")
                    continue
                if pane is not None:
                    self._pane_id_by_factory[factory] = pane.id

        # One menu-bar rebuild covers actions-only extensions too.
        try:
            rebuild_menu_bar_live(window, task, application)
        except Exception:
            logger.exception("reactive menu bar rebuild failed")

    @staticmethod
    def _matches(ext, task):
        ext_task_id = getattr(ext, "task_id", None)
        return (not ext_task_id) or ext_task_id == task.id
