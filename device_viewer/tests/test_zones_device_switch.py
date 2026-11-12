# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Zones are drawn once after a device switch (#968)."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtWidgets import QApplication, QGraphicsScene

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.services.electrode_interaction_service import (
    ElectrodeInteractionControllerService,
)
from device_viewer.services.svg_persistence_service import SvgPersistenceService
from device_viewer.utils.auto_fit_graphics_view import AutoFitGraphicsView
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.zone_view.zone_region_item import ZoneRegionItem

DEVICES = Path(__file__).resolve().parents[1] / "resources" / "devices"


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class DeviceSwitcher:
    """The dock pane's device-load sequence, minus the plugin scaffolding.

    Replaced services are kept in ``services``: in the app the service and
    its keyboard service reference each other, so a replaced one lives on
    until the cyclic GC runs.
    """

    def __init__(self):
        self.preferences = DeviceViewerPreferences()
        self.model = DeviceViewMainModel(preferences=self.preferences)
        self.persistence = SvgPersistenceService(model=self.model)
        self.scene = QGraphicsScene()
        self.view = AutoFitGraphicsView(self.scene)
        self.layer = None
        self.services = []

    def load(self, svg_file):
        self.persistence.load(str(svg_file))

        if self.layer is not None:
            self.layer.remove_all_items_to_scene(self.scene)

        default_alphas = {
            key: self.model.get_alpha(key) for key in self.preferences.default_alphas
        }
        self.layer = ElectrodeLayer(self.model.electrodes, default_alphas)
        self.layer.add_all_items_to_scene(self.scene)

        if self.services:
            self.services[-1].cleanup()

        service = ElectrodeInteractionControllerService(
            model=self.model,
            electrode_view_layer=self.layer,
            device_view=self.view,
            device_viewer_preferences=self.preferences,
        )
        self.services.append(service)
        service.zones_redraw(None)

    def add_zone(self):
        zones = self.model.zones
        zones.selected_zone_type = zones.zone_types[0]
        zones.pending_electrode_ids = list(self.model.electrodes.electrodes)[:2]
        zones.commit_pending_region()

    def zone_item_count(self):
        return sum(isinstance(item, ZoneRegionItem) for item in self.scene.items())


def test_a_zone_is_drawn_once_after_switching_devices():
    switcher = DeviceSwitcher()
    switcher.load(DEVICES / "2x3device.svg")
    switcher.add_zone()

    assert switcher.zone_item_count() == 1

    for svg_name in ("90_pin_array.svg", "2x3device.svg"):
        switcher.load(DEVICES / svg_name)

        assert switcher.zone_item_count() == 0

        switcher.add_zone()

        assert len(switcher.model.zones.regions) == 1
        assert switcher.zone_item_count() == 1
