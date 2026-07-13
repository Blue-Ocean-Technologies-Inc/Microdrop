"""PluginManagementPlugin — runtime plugin management.

Wires the reactive TASK_EXTENSIONS consumer (any plugin added to / removed
from the running application gets its dock panes mounted/unmounted and the
menu bar rebuilt automatically — the UI-side analogue of the message router's
reactive ACTOR_TOPIC_ROUTES handling), offers the PluginGroupManager service,
contributes the Tools ▸ Manage Plugins action, and restores each group's
persisted enabled state on launch.
"""

import dramatiq

from envisage.api import Plugin, SERVICE_OFFERS, ServiceOffer, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition
from pyface.api import GUI

from traits.api import Any, Bool, List, Str, observe

from microdrop_application.consts import PKG as microdrop_application_PKG
from microdrop_utils.tasks_runtime_helpers import restore_saved_task_layout

from .consts import PKG, PKG_name
from .i_plugin_group_manager import IPluginGroupManager

from . import package_installer
from .update_controller import show_update_dialog
from .update_model import compute_update_report

from logger.logger_service import get_logger
logger = get_logger(__name__)


class PluginManagementPlugin(Plugin):
    """Reactive pane/menu mounting + the plugin-group manager service + UI."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    #: The task whose Tools menu we contribute to.
    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")

    my_service_offers = List(contributes_to=SERVICE_OFFERS)
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: Cached singleton group manager (lazily built by the service factory).
    _manager = Any()

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

    # --- group-manager service -----------------------------------------

    def _my_service_offers_default(self):
        return [
            ServiceOffer(
                protocol=IPluginGroupManager,
                factory=self._create_plugin_group_manager,
            )
        ]

    def _create_plugin_group_manager(self, *args, **kwargs):
        """Factory for the group manager, cached on the plugin so every lookup
        shares one manager (and thus the loaded-group state)."""
        if self._manager is None:
            from .group_manager import PluginGroupManager
            self._manager = PluginGroupManager()
        return self._manager

    # --- menu contribution ----------------------------------------------

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        id="plugin_management.tools_actions",
                        factory=self._tools_actions_group,
                        path="MenuBar/Tools",
                    )
                ],
            )
        ]

    def _tools_actions_group(self):
        """Single Manage Plugins action in Tools."""
        from pyface.tasks.action.api import SGroup
        from .menus import ManagePluginsAction
        return SGroup(ManagePluginsAction(), id="plugin_management_actions")

    # --- launch restore ---------------------------------------------------

    #: True once the launch restore has run (it must run exactly once).
    _groups_restored = Bool(False)

    # COLON (not dot) observe: "application:application_initialized" fires only
    # when the application_initialized event fires. The dot form ALSO fires when
    # the intermediate `application` trait is assigned — i.e. at app
    # CONSTRUCTION, before the startup plugins are adoptable, which made this
    # restore enable() duplicate heater plugin instances and crash startup with
    # "duplicate base class HeaterMonitorMixinService".
    @observe("application:application_initialized")
    def _restore_groups_on_launch(self, event):
        """Adopt the startup-composed group plugins, then reconcile every
        group to its persisted enabled flag (default enabled) — so a group
        toggled off in a previous session stays off. Runs exactly once."""
        if self._groups_restored:
            return
        self._groups_restored = True
        manager = self._create_plugin_group_manager()
        try:
            manager.adopt_running(self.application)
            manager.restore_persisted(self.application)
        except Exception:
            logger.exception("plugin-group launch restore failed")

        # The reactive pane mount for any group enabled above is already
        # queued on the UI loop (LiveTaskExtensionsController defers its
        # reconcile with invoke_later), so queue the saved-layout re-apply
        # behind it: at window creation those panes did not exist yet, so
        # envisage dropped their saved placement (restore_saved_task_layout).
        GUI.invoke_later(self._reapply_saved_layout_after_launch_restore)

        self.application.extra_plugins_loaded = True

    def _reapply_saved_layout_after_launch_restore(self):
        """Give the user back their saved window layout when the enabled
        plugin set is unchanged from the previous session. Only re-applies
        when the launch restore actually hot-mounted panes — a mid-session
        Manage Plugins toggle never re-runs this, so it cannot stomp a live
        arrangement."""
        if self._live_task_exts is None or not self._live_task_exts.has_mounted_panes:
            return
        window = self.application.active_window
        if window is None:
            return
        try:
            restore_saved_task_layout(window, self.application)
        except Exception:
            logger.exception("saved-layout re-apply after launch restore failed")

    #: True once the launch update check has started (runs exactly once).
    _update_check_started = Bool(False)

    @observe("application:application_initialized")
    def _check_plugin_updates_on_launch(self, event):
        """Fetch the plugins channel in the background and, when an
        installed package has an update or new plugins appeared since the
        last launch, show the update dialog. Never blocks launch; offline
        (or any fetch failure) is silent. Colon-observe for the same
        reason as _restore_groups_on_launch above."""
        if self._update_check_started:
            return
        self._update_check_started = True
        self._make_update_check_actor().send()

    def _make_update_check_actor(self):
        """Declare the one-shot update-check actor on the shared broker.

        max_retries=0: a crash escaping the internal guards must not make
        the Retries middleware re-enqueue the check (repeated channel
        fetches, duplicate dialogs) — a failed check just waits for the
        next launch.
        """
        @dramatiq.actor(max_retries=0)
        def plugin_update_check():
            try:
                # Read the previous launch's copy BEFORE the fetch rewrites it.
                old = package_installer.read_cached_index()
                new = package_installer.search_channel()
                installed = package_installer.installed_plugin_dists()
            except package_installer.InstallError as e:
                logger.info(f"plugin update check skipped: {e}")
                return
            except Exception:
                # The design promises a silent, log-only skip on ANY failure —
                # e.g. the post-fetch cache write raising OSError (disk full /
                # read-only app home), which is not an InstallError.
                logger.exception("plugin update check failed unexpectedly")
                return
            report = compute_update_report(old, new, installed)
            if not report.has_content:
                logger.info("plugin update check: everything up to date")
                return
            logger.info(
                f"plugin update check: {len(report.updates)} update(s), "
                f"{len(report.new_plugins)} new plugin(s)"
            )
            GUI.invoke_later(show_update_dialog, report, self.application)

        return plugin_update_check
