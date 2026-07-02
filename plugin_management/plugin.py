"""PluginManagementPlugin — runtime plugin management infrastructure.

Phase C scope: wires the reactive TASK_EXTENSIONS consumer, so any plugin
added to / removed from the running application gets its dock panes mounted /
unmounted and the menu bar rebuilt automatically. This is the UI-side analogue
of what the message router already does for ACTOR_TOPIC_ROUTES.

The manage/install/uninstall orchestration and its Tools-menu UI land on top
of this in a later phase.
"""
from envisage.api import Plugin, TASK_EXTENSIONS
from traits.api import Any

from .consts import PKG, PKG_name

from logger.logger_service import get_logger
logger = get_logger(__name__)


class PluginManagementPlugin(Plugin):
    """Wires the reactive dock-pane / menu mounting for runtime plugin changes."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    #: View-layer controller that reactively mounts/unmounts dock panes +
    #: rebuilds the menu bar when TASK_EXTENSIONS change at runtime.
    _live_task_exts = Any()

    def start(self):
        """Listen for runtime TASK_EXTENSIONS changes so a hot-loaded plugin's
        dock panes get mounted and the menu bar rebuilt reactively (debounced).
        Uses the same registry mechanism connect_extension_point_traits() uses,
        applied as a consumer of the TasksApplication-owned TASK_EXTENSIONS
        extension point."""
        super().start()
        # Guard against a double start() (envisage starts a plugin once, but
        # add_extension_point_listener does not dedup — a second registration
        # would fire two reconciles per delta).
        if self._live_task_exts is None:
            from .live_task_extensions import LiveTaskExtensionsController
            self._live_task_exts = LiveTaskExtensionsController(
                application=self.application)
            self.application.add_extension_point_listener(
                self._on_task_extensions_changed, TASK_EXTENSIONS)

    def stop(self):
        super().stop()
        try:
            self.application.remove_extension_point_listener(
                self._on_task_extensions_changed, TASK_EXTENSIONS)
        except Exception as e:
            logger.debug(f"TASK_EXTENSIONS listener already removed: {e}")

    def _on_task_extensions_changed(self, registry, event):
        """Extension-registry listener: ``listener(registry, event)`` where
        ``event`` is an ExtensionPointChangedEvent carrying added/removed
        TaskExtensions. Forward the delta to the debounced controller."""
        if self._live_task_exts is not None:
            self._live_task_exts.on_changed(
                list(event.added), list(event.removed))
