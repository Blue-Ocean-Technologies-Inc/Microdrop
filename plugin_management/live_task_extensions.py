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
**defer** the reconcile to a later turn of the shared paced queue
(toolkit-agnostic, not raw Qt). Deferral has two effects:
it runs the reconcile *after* the manager's synchronous add+start loop (so panes
are created once their plugins are started), and the ``_scheduled`` guard
coalesces a whole burst of deltas into a single reconcile + a single menu
rebuild.

A reconcile mounts one dock pane per paced turn (``microdrop_utils.gui_pacing``)
and rebuilds the menu bar on a turn of its own once the last pane is in: a
pane's construction can take a large part of a second, and the window must
repaint and take input between them. Changes arriving while a reconcile runs
join it, before its menu-bar rebuild. ``call_when_settled`` runs code once the
panes and menus of the changes so far are in.

(Note: ``@observe(dispatch="ui")`` does NOT help here — traits' ui-dispatch runs
the handler inline when the change is already on the main thread, so it would
neither defer nor coalesce. The paced queue is the deferral primitive.)
"""

# Enthought library imports.
from traits.api import Any, Bool, Dict, HasTraits, List, Property, observe
from traits.observation.api import trait

# Microdrop utils imports.
from microdrop_utils.gui_pacing import invoke_paced
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

    #: The pane mounts the running reconcile still has to make, one per
    #: turn, as ``(extension, factory)`` pairs.
    _mounts = List()

    #: factory class -> the id of the pane instance we mounted for it, so we can
    #: unmount by id later (a DockPane subclass's ``id`` trait value isn't
    #: reliably readable off the class object).
    _pane_id_by_factory = Dict()

    #: True once a reconcile is queued on the UI loop — coalesces a burst of
    #: TASK_EXTENSIONS changes into one reconcile.
    _scheduled = Bool(False)

    #: True from a reconcile's start until its menu-bar rebuild is done.
    _reconciling = Bool(False)

    #: Callables waiting for the controller to settle (call_when_settled).
    _settled_callbacks = List()

    has_mounted_panes = Property(Bool)

    def _get_has_mounted_panes(self):
        """True while at least one dock pane this controller hot-mounted is
        still mounted (entries are dropped again on unmount)."""
        return bool(self._pane_id_by_factory)

    #: True while TASK_EXTENSIONS changes wait for their reconcile, e.g.
    #: because no window shows its task yet, or while a reconcile runs.
    has_pending_changes = Property(Bool)

    def _get_has_pending_changes(self):
        return bool(
            self._pending_added
            or self._pending_removed
            or self._mounts
            or self._reconciling
        )

    #: True while a reconcile is queued or running, i.e. the panes and menus
    #: of the changes so far are still coming without anything else to wait
    #: for. Changes kept until a window shows its task do not count.
    busy = Property(Bool)

    def _get_busy(self):
        return self._scheduled or self._reconciling

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

    def call_when_settled(self, callable):
        """Call ``callable()`` on a paced turn once no reconcile is queued or
        running. Changes kept until a window shows its task do not hold it
        back."""
        if self.busy:
            self._settled_callbacks.append(callable)
        else:
            invoke_paced(callable)

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
            invoke_paced(self._reconcile)

    @observe(
        trait("application", notify=False)
        .trait("active_window", optional=True)
        .trait("active_task", optional=True)
    )
    def _reconcile_once_a_task_shows(self, event):
        """Apply the changes kept while no window showed its task."""
        if self._pending_added or self._pending_removed or self._mounts:
            self._schedule_reconcile()

    def _active_window_and_task(self):
        window = getattr(self.application, "active_window", None)

        return window, getattr(window, "active_task", None)

    def _reconcile(self):
        """Start applying the pending changes, one turn per pane mount."""
        self._scheduled = False

        window, task = self._active_window_and_task()

        # Keep the changes until a window shows its task: dropping them here
        # would lose the panes and menus of every plugin loaded before then.
        # A reconcile under way takes them up before its menu-bar rebuild.
        if task is None or self._reconciling:
            self._settle()

            return

        if not (self._pending_added or self._pending_removed or self._mounts):
            self._settle()

            return

        self._reconciling = True
        self._mount_next()

    def _take_pending_changes(self, window, task):
        """Unmount the withdrawn panes now; queue the new ones' mounts."""
        added, removed = self._pending_added, self._pending_removed
        self._pending_added, self._pending_removed = [], []

        # Removed first: drop panes whose plugin is going away before mounting
        # new ones, including mounts still queued for them.
        for ext in removed:
            self._mounts = [mount for mount in self._mounts if mount[0] is not ext]

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

        self._mounts.extend(
            (ext, factory)
            for ext in added
            if self._matches(ext, task)
            for factory in getattr(ext, "dock_pane_factories", []) or []
        )

    def _mount_next(self):
        """Mount one queued pane, or rebuild the menu bar once none is left."""
        window, task = self._active_window_and_task()

        # The window closed (application exit) or shows no task: keep the
        # queue for _reconcile_once_a_task_shows.
        if task is None:
            self._reconciling = False
            self._settle()

            return

        self._take_pending_changes(window, task)

        if not self._mounts:
            self._rebuild_menu_bar(window, task)

            return

        extension, factory = self._mounts.pop(0)

        try:
            pane = add_dock_pane_live(window, task, factory)
        except Exception:
            logger.exception("reactive mount of a dock pane failed")
            pane = None

        if pane is not None:
            self._pane_id_by_factory[factory] = pane.id

        invoke_paced(self._mount_next)

    def _rebuild_menu_bar(self, window, task):
        """One menu-bar rebuild covers actions-only extensions too."""
        try:
            rebuild_menu_bar_live(window, task, self.application)
        except Exception:
            logger.exception("reactive menu bar rebuild failed")

        self._reconciling = False
        self._settle()

    def _settle(self):
        """Hand the callables waiting for a settled controller to the pacer,
        unless another reconcile is queued or running."""
        if self.busy:
            return

        callbacks, self._settled_callbacks = self._settled_callbacks, []

        for callback in callbacks:
            invoke_paced(callback)

    @staticmethod
    def _matches(ext, task):
        ext_task_id = getattr(ext, "task_id", None)
        return (not ext_task_id) or ext_task_id == task.id
