# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Plugins a run configuration starts only after the main window has painted.

A run script names each deferred plugin by its ``"module:Class"`` spec, so the
plugin's module (and whatever heavy packages it imports) is not imported
before the window is up, and declares the dock panes the plugin will
contribute, so placeholders with the final pane ids can be laid out with the
window, and may name the modules the plugin imports lazily, so they can be
imported off the GUI thread. The plugin-management loader imports, starts and
mounts them one at a time, in ``load_order``. Qt-free; it lives in
``microdrop_utils`` because the run scripts, the application and
``plugin_management`` all read it.
"""

# Standard library imports.
import importlib

# Enthought library imports.
from traits.api import Bool, Enum, HasTraits, Instance, Int, List, Property, Str

#: The priority of a deferred plugin the user should see before the others
#: have loaded, e.g. the News section of the drawer open at start-up.
PRIORITY_FIRST = 100


def load_order(deferred_plugins):
    """``deferred_plugins`` in the order they load: higher ``priority``
    first, the declaration order otherwise."""
    return sorted(deferred_plugins, key=lambda deferred: -deferred.priority)


class DeferredDockPane(HasTraits):
    """A dock pane a deferred plugin will contribute, as its placeholder shows."""

    #: The pane's id, exactly as the real pane sets it.
    id = Str()

    #: The pane's title, shown on its placeholder and in the View menu.
    name = Str()

    #: Where the pane docks when no saved layout places it.
    dock_area = Enum("left", "right", "top", "bottom")

    #: Whether the pane shows when no saved layout places it.
    visible = Bool(False)


class DeferredPlugin(HasTraits):
    """A plugin started after the main window paints, and the panes it adds."""

    #: The plugin class as ``"module:Class"``, imported only when it loads.
    spec = Str()

    #: The dock panes the plugin contributes, declared ahead of its import.
    dock_panes = List(Instance(DeferredDockPane))

    #: Modules the plugin imports only once it is added, started or builds
    #: its panes (lazy imports in its contribution defaults and pane
    #: factories). The loader imports them with the plugin's own module on a
    #: worker thread, so the GUI thread does not.
    preload_modules = List(Str)

    #: Plugins load highest priority first, those of equal priority in the
    #: order declared (``load_order``). Their order in the application
    #: decides service and extension precedence, and a plugin needing
    #: another (a UI its service) is declared after it, so raise it only
    #: for a plugin that needs, and contributes ahead of, no other deferred
    #: plugin.
    priority = Int(0)

    #: The class part of ``spec``, the plugin's name until it is imported.
    class_name = Property(Str, observe="spec")

    #: The plugin's own module, then ``preload_modules``.
    module_names = Property(List(Str), observe="spec, preload_modules.items")

    def _get_class_name(self):
        return self.spec.partition(":")[2]

    def _get_module_names(self):
        return [self.spec.partition(":")[0], *self.preload_modules]

    @property
    def __name__(self):
        """The plugin class's name, as the class itself would give it.

        Launchers list and select plugins by ``plugin.__name__``; a deferred
        plugin stands in for its class there without being imported.
        """
        return self.class_name

    def import_class(self):
        """Import and return the plugin class ``spec`` names."""
        module_path, _, class_name = self.spec.partition(":")
        module = importlib.import_module(module_path)

        return getattr(module, class_name)
