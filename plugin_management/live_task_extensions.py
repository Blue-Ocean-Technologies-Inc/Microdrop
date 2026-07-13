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

from pyface.api import GUI
from traits.api import Any, Bool, Dict, HasTraits, List, Property

from microdrop_utils.tasks_runtime_helpers import (
    add_dock_pane_live, rebuild_menu_bar_live, remove_dock_pane_live,
)
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

    def on_changed(self, added, removed):
        """Record a TASK_EXTENSIONS delta and schedule one deferred reconcile."""
        self._pending_added.extend(added)
        self._pending_removed.extend(removed)
        if not self._scheduled:
            self._scheduled = True
            GUI.invoke_later(self._reconcile)

    # --- internals ---------------------------------------------------

    def _reconcile(self):
        self._scheduled = False
        added, removed = self._pending_added, self._pending_removed
        self._pending_added, self._pending_removed = [], []

        application = self.application
        window = getattr(application, "active_window", None)
        if window is None:
            return
        task = getattr(window, "active_task", None)
        if task is None:
            return

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
