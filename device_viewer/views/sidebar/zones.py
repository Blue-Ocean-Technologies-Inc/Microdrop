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
from ...controllers.zones_controller import ZonesController
from ..zone_view.zones_sidebar import zones_view
from .section import SidebarSection


class ZonesSection(SidebarSection):
    """The Zones section and the objects its widget depends on."""

    #: Zones editor UI; the pane sizes its zone-type table from preferences.
    zones_ui = Instance(UI)

    #: Keeps zone edits in step with the main model.
    zones_controller = Instance(ZonesController)


def build_zones(model):
    """Build the Zones section for the main model."""
    zones_controller = ZonesController(model=model)
    zones_ui = model.zones.edit_traits(view=zones_view)

    return ZonesSection(
        title="Zones",
        widget=zones_ui.control,
        zones_ui=zones_ui,
        zones_controller=zones_controller,
    )
