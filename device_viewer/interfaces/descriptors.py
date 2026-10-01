# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Value records a device viewer layer hands the base (#650).

Part of the public layer contract: layer plugins import these through
``device_viewer.consts``. Kept free of Qt and of ``device_viewer`` imports so
importing ``device_viewer.consts`` stays cheap and cycle-free; Qt types are
named by string and resolved on first use.
"""

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance, Range, Str


class AlphaEntry(HasTraits):
    """One row a layer adds to the device viewer's layer-opacity table."""

    #: Row label, and its key in ``model.alpha_map`` and in the saved
    #: ``default_alphas`` / ``default_visibility`` preferences.
    key = Str()

    #: Opacity in percent on first run; afterwards the saved value wins.
    alpha = Range(0, 100, 100)

    #: Visibility on first run; afterwards the saved value wins.
    visible = Bool(True)


class InteractionMode(HasTraits):
    """One value a layer adds to the device viewer's ``model.mode``."""

    #: The mode's value, unique across the base and every layer
    #: (e.g. "zone-select").
    id = Str()

    #: Status-bar hint shown while the mode is active; empty for none.
    status_message = Str()


class SidebarSection(HasTraits):
    """One collapsible section of the device viewer sidebar.

    The built-in sidebar builders return one, and so does a layer's
    ``build_sidebar_section(parent)``; the sidebar host stacks the sections
    in order, each in its own collapsible box.
    """

    #: Header text of the section's collapsible box.
    title = Str()

    #: The section's content.
    widget = Instance("pyface.qt.QtWidgets.QWidget")

    #: Whether the section starts collapsed.
    collapsed = Bool(False)
