# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""Sidebar section: electrode zone types and regions."""

# Enthought library imports.
from traits.api import Instance
from traitsui.api import UI

# Local imports.
from ..zone_view.zones_sidebar import zones_view
from .section import SizedSidebarSection


class ZonesSection(SizedSidebarSection):
    """The Zones section; its ZonesController lives with the pane, since
    zone edits reach the model before the section is built."""

    #: Zones editor UI; its zone-type table is sized from preferences.
    zones_ui = Instance(UI)

    def apply_sizes(self, preferences):
        zone_types_editor = self.zones_ui.get_editors("zone_types")[0]
        zone_types_editor.control.setMinimumHeight(preferences.ZONES_VIEW_MIN_HEIGHT)


def build_zones(model):
    """Build the Zones section for the main model."""
    zones_ui = model.zones.edit_traits(view=zones_view)

    return ZonesSection(title="Zones", widget=zones_ui.control, zones_ui=zones_ui)
