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
window. The plugin-management loader imports, starts and mounts them one at a
time. Qt-free; it lives in ``microdrop_utils`` because the run scripts, the
application and ``plugin_management`` all read it.
"""

# Standard library imports.
import importlib

# Enthought library imports.
from traits.api import Bool, Enum, HasTraits, Instance, List, Property, Str


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

    #: The class part of ``spec``, the plugin's name until it is imported.
    class_name = Property(Str, observe="spec")

    def _get_class_name(self):
        return self.spec.partition(":")[2]

    def import_class(self):
        """Import and return the plugin class ``spec`` names."""
        module_path, _, class_name = self.spec.partition(":")
        module = importlib.import_module(module_path)

        return getattr(module, class_name)
