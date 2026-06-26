"""Service interface for the plugin-group orchestrator.

Consumers (the Tools actions, the launch-restore hook, the installer) depend on
this interface rather than the concrete ``PluginGroupManager``, so the service
is offered and looked up by ``IPluginGroupManager`` — decoupling callers from
the implementation (traits ``@provides`` pattern)."""

from traits.api import Dict, Interface, Str


class IPluginGroupManager(Interface):
    """Discovers plugin groups from manifests and hot loads/unloads them."""

    #: {group_name: PluginGroup} of every discovered group.
    groups = Dict(Str)

    def is_loaded(self, group_name):
        """True if the named group is currently loaded."""

    def enable(self, task, group_name):
        """Hot-load the named group (add+start its plugins, mount its dock
        panes, rebuild the menu bar, run its post-enable publish)."""

    def disable(self, task, group_name):
        """Hot-unload the named group (the reverse of enable)."""

    def apply(self, task, desired):
        """Reconcile group load state to ``desired`` ({group_name: bool})."""

    def installed_plugins(self):
        """List ``(name, label, dist_name, [group_names])`` for each
        user-installed plugin (bundled ones excluded)."""

    def installed_plugin(self, manifest_name):
        """The ``installed_plugins()`` entry for ``manifest_name``, or None."""

    def register_manifest(self, manifest, dist_name=""):
        """Register a freshly-installed manifest's groups at runtime."""

    def deregister_plugin(self, manifest_name):
        """Drop a plugin's groups and clear their persisted enabled flags."""
