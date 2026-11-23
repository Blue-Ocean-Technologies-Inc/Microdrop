# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Start the run configuration's deferred plugins once the window is up.

Each deferred plugin loads on its own event-loop turn: import its module,
construct it, add it to the application and start it through the isolating
plugin manager, which records the start and withdraws the plugin if it
fails. Adding it contributes its task extensions, so the live task-extension
controller mounts its panes (replacing their placeholders) and rebuilds the
menu bar on the next turn; the turn after that checks the panes against the
declaration and moves on to the next plugin. The window repaints and takes
input between the turns. A plugin that fails, its import included, is
recorded and skipped; ``finished`` fires once after the last one.

Qt-free: it schedules its turns with ``pyface.api.GUI.invoke_later``.
"""

# Standard library imports.
import time
import traceback

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, IApplication
from pyface.api import GUI
from traits.api import Bool, Event, Float, HasTraits, Instance, List

# Microdrop utils imports.
from microdrop_utils.deferred_plugins import DeferredPlugin
from microdrop_utils.isolating_plugin_manager import withdraw_plugin
from microdrop_utils.plugin_load_status import PluginLoadStatus, summarize_exception

# Local imports.
from .live_task_extensions import LiveTaskExtensionsController

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def compare_declared_panes(declared_ids, mounted_ids):
    """Split a deferred plugin's pane ids into declared-only and mounted-only.

    Returns
    -------
    tuple of list
        The declared ids no pane was mounted for, and the mounted ids the
        declaration does not name.
    """
    missing = [pane_id for pane_id in declared_ids if pane_id not in mounted_ids]
    undeclared = [pane_id for pane_id in mounted_ids if pane_id not in declared_ids]

    return missing, undeclared


class DeferredPluginLoader(HasTraits):
    """Load deferred plugins one per event-loop turn and record each."""

    #: The application the plugins join. Its plugin manager must be an
    #: ``IsolatingPluginManager``.
    application = Instance(IApplication)

    #: The plugins to load, in order.
    deferred_plugins = List(Instance(DeferredPlugin))

    #: Where every plugin's load is recorded.
    load_status = Instance(PluginLoadStatus)

    #: Mounts the plugins' panes; set when loading starts.
    live_task_extensions = Instance(LiveTaskExtensionsController)

    #: True from ``start()`` until the last plugin has been handled.
    running = Bool(False)

    #: Fired once, after every deferred plugin has loaded or failed.
    finished = Event()

    #: The plugins still to load.
    _queue = List(Instance(DeferredPlugin))

    #: ``time.perf_counter()`` when loading started.
    _started_at = Float()

    def mark_pending(self):
        """Record every deferred plugin as pending, under its spec."""
        for deferred in self.deferred_plugins:
            self.load_status.mark_pending(deferred.spec, deferred.class_name)

    def record_for(self, deferred):
        """Return ``deferred``'s load record, pending until it loads."""
        record = self.load_status.get_record(deferred.spec)

        if record is None:
            record = self.load_status.mark_pending(deferred.spec, deferred.class_name)

        return record

    def start(self, live_task_extensions=None):
        """Begin loading, one plugin per event-loop turn."""
        if self.running:
            return

        self.live_task_extensions = live_task_extensions
        self._queue = list(self.deferred_plugins)
        self._started_at = time.perf_counter()
        self.running = True

        GUI.invoke_later(self._load_next)

    # --- turns ------------------------------------------------------------

    def _load_next(self):
        """Load the next plugin, or finish when none is left."""
        if not self._queue:
            self._finish()

            return

        deferred = self._queue.pop(0)

        try:
            plugin = self._load(deferred)

        # Whatever goes wrong, the plugins after this one must still load.
        except Exception:
            logger.exception(f"Loading deferred plugin {deferred.spec} failed")
            plugin = None

        # The live controller queued the plugin's pane mounts while it was
        # added; these run after them, in order.
        if plugin is not None:
            GUI.invoke_later(self._check_panes, deferred, plugin)

        GUI.invoke_later(self._load_next)

    def _load(self, deferred):
        """Import, construct, add and start one plugin.

        Returns
        -------
        Plugin or None
            The started plugin, or None if it failed (and was withdrawn).
        """
        record = self.record_for(deferred)
        started_at = time.perf_counter()

        try:
            plugin = deferred.import_class()()

        except Exception as error:
            logger.error(f"Deferred plugin {deferred.spec} failed to import")
            self.load_status.mark_failed(
                deferred.spec,
                summarize_exception(error),
                traceback.format_exc(),
                time.perf_counter() - started_at,
            )

            return None

        # From here on the record follows the plugin's own id, as the
        # plugin manager records its start under it.
        record.trait_set(plugin_id=plugin.id, name=plugin.name)

        try:
            self.application.add_plugin(plugin)

        except Exception as error:
            logger.error(f"Deferred plugin {plugin.id} could not be added")
            self.load_status.mark_failed(
                plugin.id, summarize_exception(error), traceback.format_exc()
            )
            withdraw_plugin(self.application, plugin)

            return None

        if not self.application.plugin_manager.start_isolated(plugin):
            return None

        logger.info(
            f"Deferred plugin {plugin.id} started in "
            f"{time.perf_counter() - started_at:.3f} s"
        )

        return plugin

    def _check_panes(self, deferred, plugin):
        """Warn when the plugin's panes differ from its declaration.

        A declared pane the plugin did not contribute would keep its
        placeholder forever, so that placeholder is taken down.
        """
        controller = self.live_task_extensions

        if controller is None or controller.has_pending_changes:
            logger.debug(f"Panes of {plugin.id} not mounted yet; not checked")

            return

        declared = [pane.id for pane in deferred.dock_panes]
        mounted = controller.mounted_pane_ids(plugin.get_extensions(TASK_EXTENSIONS))
        missing, undeclared = compare_declared_panes(declared, mounted)

        if not (missing or undeclared):
            return

        logger.warning(
            f"Deferred plugin {deferred.spec} declares dock panes {declared} "
            f"but contributed {mounted}: update its declaration in the run "
            "configuration"
        )

        for pane_id in missing:
            controller.unmount_pane(pane_id)

    def _finish(self):
        self.running = False
        elapsed = time.perf_counter() - self._started_at

        logger.info(
            f"Deferred plugins finished in {elapsed:.3f} s: {self.load_status.summary}"
        )

        self.finished = True
