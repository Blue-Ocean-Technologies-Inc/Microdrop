"""Runtime hot load/unload of *named groups* of Envisage plugins.

Groups are discovered from microdrop_plugin.json manifests — bundled ones in
the repo's default_plugins/ and user-installed ones under the app-data
installed_plugins/ dir (see plugin_management). Each group names
its plugin classes as dotted "module:Class" specs, resolved lazily at enable
time so a broken/installed plugin never breaks startup or discovery.

Envisage supports adding/removing plugins at runtime, but three layers don't
self-heal: runtime ServiceOffers leak (CorePlugin discards their ids), Pyface
Tasks never adds a dock pane after the window is shown, and a plugin's backend
resources outlive a bare stop(). This orchestrator fills the first two
generically (service-id capture + live dock-pane mount/unmount) and relies on
each plugin's own stop() for the third. The menu bar is rebuilt on each
enable/disable so plugin-contributed submenus appear/disappear live.
"""

import importlib
from pathlib import Path

from traits.api import Bool, Dict, HasTraits, Instance, List, Str, provides

from microdrop_application.helpers import get_microdrop_redis_globals_manager
from plugin_management import paths
from plugin_management.manifest import load_manifest, ManifestError
from plugin_management.i_plugin_group_manager import IPluginGroupManager
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

logger = get_logger(__name__)

app_globals = get_microdrop_redis_globals_manager()


class PluginGroup(HasTraits):
    """One named, ordered set of plugins that load/unload together."""

    name = Str()
    #: User-visible label (shown in the Manage Plugins dialog).
    label = Str()
    #: Plugin classes as dotted "module:Class" specs, in load order (unloaded
    #: in reverse). Resolved to classes lazily at enable time.
    plugin_specs = List(Str)
    #: Live plugin instances while loaded (empty otherwise).
    instances = List()
    #: Service-registry ids registered while the group loaded, captured by a
    #: before/after snapshot so disable() can unregister exactly them.
    service_ids = List()
    loaded = Bool(False)
    #: App-globals flag persisting this group's enabled state across runs.
    enabled_key = Str()
    #: Optional topic published (empty message) right after a successful
    #: enable — e.g. the backend group kicks off the magnet search.
    post_enable_publish_topic = Str()
    #: The owning manifest's name + label, and the directory the manifest was
    #: discovered/installed from. Used to list and uninstall user-installed
    #: plugins (those whose source_dir is under installed_plugins/).
    manifest_name = Str()
    manifest_label = Str()
    source_dir = Str()


@provides(IPluginGroupManager)
class PluginGroupManager(HasTraits):
    """Discovers, loads, and unloads named plugin groups against a live
    application. Offered as an Envisage service by MicrodropPlugin; the
    Install/Manage Plugins actions and the launch-restore hook use it."""

    groups = Dict(Str, Instance(PluginGroup))

    def _groups_default(self):
        return self._discover_groups()

    # --- discovery ---------------------------------------------------

    def _discover_groups(self):
        """Build the group map from every manifest in default_plugins/ and
        installed_plugins/. Reads JSON only (no plugin imports), so a broken
        installed plugin can't break discovery."""
        groups = {}
        for manifest_dir in paths.iter_manifest_dirs():
            manifest_path = manifest_dir / paths.MANIFEST_FILENAME
            try:
                manifest = load_manifest(manifest_path)
            except ManifestError:
                logger.exception(f"skipping invalid manifest at {manifest_path}")
                continue
            self._add_manifest_groups(
                manifest, source_dir=str(manifest_dir), into=groups)
        from plugin_management import entry_point_discovery
        if entry_point_discovery.enabled():
            for manifest, source in entry_point_discovery.discover_entry_point_manifests():
                self._add_manifest_groups(manifest, source_dir=source, into=groups)
        return groups

    def _add_manifest_groups(self, manifest, source_dir="", into=None):
        """Create a PluginGroup per spec in ``manifest`` and put it in ``into``
        (defaults to self.groups). ``source_dir`` is the dir the manifest came
        from (recorded for uninstall). Last writer wins on a name collision."""
        target = self.groups if into is None else into
        for spec in manifest.groups:
            target[spec.name] = PluginGroup(
                name=spec.name,
                label=spec.label,
                plugin_specs=list(spec.plugins),
                enabled_key=spec.enabled_key,
                post_enable_publish_topic=spec.post_enable_publish_topic,
                manifest_name=manifest.name,
                manifest_label=manifest.label,
                source_dir=source_dir,
            )

    def register_manifest(self, manifest, source_dir=""):
        """Register a freshly-installed manifest's groups at runtime. Refuses
        (raises) if a colliding group name is currently loaded — the caller
        should ask the user to disable it first."""
        for spec in manifest.groups:
            existing = self.groups.get(spec.name)
            if existing is not None and existing.loaded:
                raise RuntimeError(
                    f"group '{spec.name}' is currently enabled; disable it "
                    f"before reinstalling"
                )
        self._add_manifest_groups(manifest, source_dir=source_dir)

    def installed_plugins(self):
        """User-installed plugins (whose source_dir sits directly under
        installed_plugins/), one entry per distinct owning manifest, as
        (name, label, source_dir, [group_names]) in discovery order. Bundled
        (default_plugins/) plugins are excluded — they can't be uninstalled."""
        try:
            base = paths.installed_plugins_dir().resolve()
        except OSError:
            return []
        out = {}
        for group in self.groups.values():
            if not group.source_dir:
                continue
            try:
                under = Path(group.source_dir).resolve().parent == base
            except OSError:
                under = False
            if not under:
                continue
            entry = out.get(group.manifest_name)
            if entry is None:
                entry = (group.manifest_name,
                         group.manifest_label or group.manifest_name,
                         group.source_dir, [])
                out[group.manifest_name] = entry
            entry[3].append(group.name)
        return list(out.values())

    def installed_plugin(self, manifest_name):
        """The installed_plugins() entry for ``manifest_name``, or None if it
        isn't a user-installed plugin."""
        for entry in self.installed_plugins():
            if entry[0] == manifest_name:
                return entry
        return None

    def deregister_plugin(self, manifest_name):
        """Drop every group owned by ``manifest_name`` from the registry and
        clear its persisted enabled flag. Used by uninstall."""
        for name in [n for n, g in self.groups.items()
                     if g.manifest_name == manifest_name]:
            group = self.groups.pop(name)
            if group.enabled_key:
                try:
                    if group.enabled_key in app_globals:
                        del app_globals[group.enabled_key]
                except Exception as e:
                    logger.debug(f"could not clear flag {group.enabled_key}: {e}")

    # --- public API --------------------------------------------------

    def is_loaded(self, group_name):
        group = self.groups.get(group_name)
        return bool(group is not None and group.loaded)

    def apply(self, task, desired):
        """Reconcile group load state to ``desired`` ({group_name: bool}).
        Enables newly-on groups in registration order; disables newly-off
        groups in reverse. Only groups whose desired state differs are
        touched."""
        names = list(self.groups.keys())
        for group_name in names:
            if desired.get(group_name) and not self.is_loaded(group_name):
                self.enable(task, group_name)
        for group_name in reversed(names):
            if (group_name in desired
                    and not desired[group_name]
                    and self.is_loaded(group_name)):
                self.disable(task, group_name)

    def enable(self, task, group_name):
        """Resolve the group's plugin specs, add + start them, capture the
        services they register, and run the optional post-enable publish.
        Idempotent — a no-op if the group is already loaded.

        Dock panes + the menu bar are mounted/rebuilt **reactively** by
        ``LiveTaskExtensionsController`` when these plugins contribute their
        TASK_EXTENSIONS — this method no longer touches the view layer."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"enable: unknown plugin group '{group_name}'")
            return
        if group.loaded:
            logger.info(f"enable: group '{group_name}' already loaded")
            return

        try:
            factories = self._resolve_factories(group)
        except Exception:
            logger.exception(
                f"enable: could not import plugin classes for '{group_name}'; "
                f"group not loaded"
            )
            return

        application = task.window.application
        registry = application.service_registry
        before = set(registry._services.keys())

        for factory in factories:
            try:
                plugin = factory()
                application.add_plugin(plugin)
                application.start_plugin(plugin)
                group.instances.append(plugin)
                logger.info(f"enable: started {plugin.id}")
            except Exception:
                logger.exception(
                    f"enable: failed to load {getattr(factory, '__name__', factory)}"
                )

        group.service_ids = sorted(set(registry._services.keys()) - before)
        logger.info(f"enable: captured service ids {group.service_ids}")

        # Optional post-enable kick — the backend group starts the magnet search.
        if group.post_enable_publish_topic:
            try:
                publish_message(topic=group.post_enable_publish_topic, message="")
                logger.info(f"enable: published {group.post_enable_publish_topic}")
            except Exception:
                logger.exception(
                    f"enable: failed to publish {group.post_enable_publish_topic}"
                )

        group.loaded = True
        if group.enabled_key:
            app_globals[group.enabled_key] = True
        logger.info(f"enable: group '{group_name}' loaded")

    def disable(self, task, group_name):
        """Reverse of enable: stop + remove every plugin (reverse order) and
        unregister the captured services. Idempotent — a no-op if the group
        isn't loaded.

        The contributed dock panes are unmounted and the menu bar rebuilt
        **reactively** by ``LiveTaskExtensionsController`` when ``remove_plugin``
        withdraws each plugin's TASK_EXTENSIONS."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"disable: unknown plugin group '{group_name}'")
            return
        if not group.loaded:
            logger.info(f"disable: group '{group_name}' not loaded")
            return

        application = task.window.application

        for plugin in reversed(group.instances):
            pid = getattr(plugin, "id", plugin)
            try:
                application.stop_plugin(plugin)
            except Exception:
                logger.exception(f"disable: stop_plugin failed for {pid}")
            try:
                application.remove_plugin(plugin)
            except Exception:
                logger.exception(f"disable: remove_plugin failed for {pid}")
            logger.info(f"disable: removed {pid}")
        group.instances = []

        for service_id in group.service_ids:
            try:
                application.unregister_service(service_id)
                logger.info(f"disable: unregistered service id {service_id}")
            except Exception:
                logger.exception(f"disable: unregister_service failed for {service_id}")
        group.service_ids = []

        group.loaded = False
        if group.enabled_key:
            app_globals[group.enabled_key] = False
        logger.info(f"disable: group '{group_name}' unloaded")

    # --- helpers -----------------------------------------------------

    def _resolve_factories(self, group):
        """Import each "module:Class" spec to a plugin class. Raises on the
        first failure so the caller aborts the enable (no partial load)."""
        factories = []
        for spec in group.plugin_specs:
            module_path, _, class_name = spec.partition(":")
            module = importlib.import_module(module_path)
            factories.append(getattr(module, class_name))
        return factories
