# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Service interface for the plugin-group manager.

Consumers (the Manage Plugins dialog, the launch-restore hook) look this up
via ``application.get_service(IPluginGroupManager)`` instead of importing the
concrete manager — the same decoupling every other cross-plugin service uses.
"""
from traits.api import Dict, Interface


class IPluginGroupManager(Interface):
    """Runtime hot load/unload of named groups of Envisage plugins."""

    #: group name -> PluginGroup.
    groups = Dict()

    def register_manifest(self, manifest, dist_name="") -> None:
        """Register a freshly-installed manifest's groups at runtime. Raises
        if a colliding group name is currently loaded."""

    def is_loaded(self, group_name) -> bool:
        """True if the named group is currently loaded."""

    def enable(self, application, group_name) -> None:
        """Resolve, add and start the group's plugins. Idempotent."""

    def disable(self, application, group_name) -> None:
        """Stop and remove the group's plugins (reverse order). Idempotent."""

    def apply(self, application, desired) -> None:
        """Reconcile load state to ``desired`` ({group_name: bool})."""

    def adopt_running(self, application) -> None:
        """Mark groups whose plugins were startup-registered as loaded,
        adopting the live instances so disable() can manage them."""

    def restore_persisted(self, application) -> None:
        """Apply each group's persisted enabled flag (default: enabled)."""
