# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the device viewer layer contract (#650)."""

# Enthought library imports.
from traits.api import List

# Microdrop package imports.
from device_viewer.consts import (
    LAYER_CONTRACT_VERSION,
    BaseDeviceViewerLayer,
    IDeviceViewerLayer,
    LayerContext,
    SidebarSection,
)
from device_viewer.views.sidebar.section import SidebarSection as SidebarSectionView


class LifecycleOnlyLayer(BaseDeviceViewerLayer):
    """Implements only the lifecycle, as the gamepad layer will."""

    #: Hook names in call order.
    calls = List()

    def attach(self, context):
        super().attach(context)
        self.calls.append("attach")

    def detach(self):
        self.calls.append("detach")
        super().detach()


def test_sibling_plugins_import_the_contract_from_consts():
    assert IDeviceViewerLayer.__module__.startswith("device_viewer.interfaces")
    assert LAYER_CONTRACT_VERSION.count(".") == 2


def test_the_sidebar_section_is_the_contract_type():
    assert SidebarSectionView is SidebarSection


def test_a_partial_layer_provides_the_interface_through_the_defaults():
    layer = LifecycleOnlyLayer(id="gamepad")

    assert isinstance(layer, IDeviceViewerLayer)
    assert layer.priority == 50
    assert layer.alpha_entries == []
    assert layer.modes == []
    assert layer.interaction_handler is None
    assert layer.svg_codec is None


def test_the_defaults_are_no_ops():
    layer = LifecycleOnlyLayer(id="gamepad")
    payload = {}

    assert layer.build_sidebar_section(parent=None) is None

    layer.on_device_loaded(electrodes=None)
    layer.on_alpha_changed("Zones", 0.5)
    layer.contribute_state(payload)
    layer.apply_state(message=None)

    assert payload == {}


def test_attach_keeps_the_context_until_detach():
    layer = LifecycleOnlyLayer(id="gamepad")
    context = LayerContext()

    layer.attach(context)

    assert layer.context is context

    layer.detach()

    assert layer.context is None
    assert layer.calls == ["attach", "detach"]
