"""Reactively mount/unmount dock panes and rebuild the menu bar when plugins
contribute/withdraw TASK_EXTENSIONS at runtime.

Pyface Tasks gathers a task's dock panes + menu bar once at window creation, so
a plugin loaded afterwards needs its panes mounted and the menu rebuilt on the
live window (see ``microdrop_utils/tasks_runtime_helpers``). This controller
turns that from imperative ``PluginGroupManager`` calls into a reactive,
debounced reconcile driven by the TASK_EXTENSIONS extension point — so *any*
runtime-loaded plugin's panes/menu appear automatically.

Qt is used here on purpose: this is a view-layer controller, not a model or
service. The reconcile is **deferred** to the GUI event loop (the debounce
timer), so it runs after the manager's synchronous add+start loop — by which
point the contributing plugins are fully started.
"""

from pyface.qt.QtCore import QTimer

from microdrop_utils.tasks_runtime_helpers import (
    add_dock_pane_live, rebuild_menu_bar_live, remove_dock_pane_live,
)
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Coalesce a burst of TASK_EXTENSIONS changes (e.g. a multi-plugin group load)
#: into a single reconcile, this many milliseconds after the burst settles.
DEBOUNCE_MS = 50


class LiveTaskExtensionsController:
    """Mount/unmount dock panes + rebuild the menu bar for TaskExtensions added
    or removed at runtime, debounced and deferred to the GUI event loop."""

    def __init__(self, application):
        self._application = application
        self._pending_added = []
        self._pending_removed = []
        #: factory class -> the id of the pane instance we mounted for it, so we
        #: can unmount by id later (a DockPane subclass's ``id`` trait value
        #: isn't reliably readable off the class object).
        self._pane_id_by_factory = {}
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reconcile)

    def on_changed(self, added, removed):
        """Record a TASK_EXTENSIONS delta and (re)start the debounce timer.
        Restarting coalesces a burst into one reconcile after it settles."""
        self._pending_added.extend(added)
        self._pending_removed.extend(removed)
        self._timer.start(DEBOUNCE_MS)

    def dispose(self):
        """Stop the debounce timer (call on plugin stop)."""
        try:
            self._timer.stop()
        except Exception:
            pass

    # --- internals ---------------------------------------------------

    def _reconcile(self):
        added, removed = self._pending_added, self._pending_removed
        self._pending_added, self._pending_removed = [], []

        window = getattr(self._application, "active_window", None)
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
            rebuild_menu_bar_live(window, task, self._application)
        except Exception:
            logger.exception("reactive menu bar rebuild failed")

    @staticmethod
    def _matches(ext, task):
        ext_task_id = getattr(ext, "task_id", None)
        return (not ext_task_id) or ext_task_id == task.id
