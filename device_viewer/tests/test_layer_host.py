# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the host that mounts device viewer layers on a pane (#650)."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from envisage.api import Application, Plugin
from pyface.qt.QtWidgets import QApplication, QLabel
from traits.api import HasTraits, List, Str, provides

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_LAYERS,
    AlphaEntry,
    BaseDeviceViewerLayer,
    IInteractionHandler,
    InteractionMode,
    LayerContext,
    SidebarSection,
)
from device_viewer.controllers.layer_host import LayerHost
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.plugin import DeviceViewerPlugin
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.views.sidebar.host import build_sidebar

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import CollapsibleVStackBox

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@provides(IInteractionHandler)
class RecordingHandler(HasTraits):
    #: (hook, mode, other mode) in call order.
    calls = List()

    def on_enter(self, mode, previous_mode):
        self.calls.append(("enter", mode, previous_mode))

    def on_exit(self, mode, next_mode):
        self.calls.append(("exit", mode, next_mode))


class StubLayer(BaseDeviceViewerLayer):
    #: Hook names in call order.
    calls = List()

    #: Title of the sidebar section to build; empty for none.
    section_title = Str()

    def attach(self, context):
        super().attach(context)
        self.calls.append("attach")

    def on_device_loaded(self, electrodes):
        self.calls.append("device_loaded")

    def detach(self):
        self.calls.append("detach")
        super().detach()

    def build_sidebar_section(self, parent):
        if not self.section_title:
            return None

        return SidebarSection(title=self.section_title, widget=QLabel())

    def on_alpha_changed(self, key, opacity):
        self.calls.append(("alpha", key, opacity))


def _factory(**traits):
    """A zero-arg layer factory, as a plugin contributes one."""

    def factory():
        return StubLayer(**traits)

    return factory


@pytest.fixture
def model():
    return DeviceViewMainModel(preferences=DeviceViewerPreferences())


@pytest.fixture
def host(model):
    sidebar = build_sidebar(
        [SidebarSection(title=title, widget=QLabel()) for title in ("A", "B")]
    )

    return LayerHost(context=LayerContext(model=model), sidebar=sidebar)


def _box_titles(host):
    layout = host.sidebar.widget().layout()

    return [
        layout.itemAt(index).widget().toggle_button.text()
        for index in range(layout.count())
        if isinstance(layout.itemAt(index).widget(), CollapsibleVStackBox)
    ]


def test_layers_are_ordered_by_priority_then_id(host):
    host.add_layers(
        [
            _factory(id="zones", priority=20),
            _factory(id="camera", priority=10),
            _factory(id="paths", priority=10),
        ]
    )

    assert [layer.id for layer in host.layers] == ["camera", "paths", "zones"]


def test_a_duplicate_id_is_dropped_and_the_first_wins(host):
    host.add_layers([_factory(id="zones", priority=30), _factory(id="zones")])
    host.add_layers([_factory(id="zones", priority=1)])

    assert [(layer.id, layer.priority) for layer in host.layers] == [("zones", 30)]


def test_a_failing_factory_or_attach_is_skipped(host):
    def broken_factory():
        raise RuntimeError("missing optional dependency")

    class BrokenAttachLayer(StubLayer):
        def attach(self, context):
            raise RuntimeError("no device view")

    host.add_layers(
        [broken_factory, lambda: BrokenAttachLayer(id="bad"), _factory(id="ok")]
    )

    assert [layer.id for layer in host.layers] == ["ok"]


def test_attach_and_detach_run_once_each(host):
    factory = _factory(id="gamepad")

    host.add_layers([factory])
    (layer,) = host.layers
    host.remove_layers([factory])

    assert layer.calls == ["attach", "detach"]
    assert layer.context is None
    assert host.layers == []


def test_sections_follow_the_built_in_ones_in_layer_order(host):
    late = _factory(id="zones", priority=20, section_title="Zones")

    host.add_layers([late, _factory(id="none", priority=15)])
    host.add_layers([_factory(id="paths", priority=10, section_title="Paths")])

    assert _box_titles(host) == ["A", "B", "Paths", "Zones"]

    host.remove_layers([late])

    assert _box_titles(host) == ["A", "B", "Paths"]


def test_sections_stay_above_the_trailing_stretch(host):
    host.add_layers([_factory(id="zones", section_title="Zones")])
    layout = host.sidebar.widget().layout()

    assert layout.itemAt(layout.count() - 1).spacerItem() is not None


def test_alpha_rows_are_added_routed_and_removed(host, model):
    factory = _factory(id="zones", alpha_entries=[AlphaEntry(key="Heat Map", alpha=40)])

    host.add_layers([factory])
    (layer,) = host.layers
    row = model.alpha_map[-1]

    assert (row.key, row.alpha) == ("Heat Map", 40)

    row.alpha = 50

    assert layer.calls[-1] == ("alpha", "Heat Map", 0.5)

    host.remove_layers([factory])

    assert "Heat Map" not in [row.key for row in model.alpha_map]


def test_an_existing_alpha_row_is_not_taken_over(host, model):
    existing = model.alpha_map[0].key
    rows = len(model.alpha_map)

    factory = _factory(id="zones", alpha_entries=[AlphaEntry(key=existing)])
    host.add_layers([factory])
    host.remove_layers([factory])

    assert len(model.alpha_map) == rows
    assert model.alpha_map[0].key == existing


def test_modes_are_registered_dispatched_and_withdrawn(host, model):
    handler = RecordingHandler()
    factory = _factory(
        id="zones",
        modes=[InteractionMode(id="zone-pick")],
        interaction_handler=handler,
    )

    host.add_layers([factory])
    model.mode = "edit"
    model.mode = "zone-pick"

    assert "zone-pick" in model.available_modes
    assert handler.calls == [("enter", "zone-pick", "edit")]

    host.remove_layers([factory])

    assert model.mode == "display"
    assert model.last_mode == "display"
    assert "zone-pick" not in model.available_modes
    assert handler.calls[-1] == ("exit", "zone-pick", "display")


def test_a_base_mode_is_not_taken_over(host, model):
    factory = _factory(id="paths", modes=[InteractionMode(id="draw")])

    host.add_layers([factory])
    host.remove_layers([factory])

    assert "draw" in model.available_modes


def test_device_load_reaches_every_layer(host):
    host.add_layers([_factory(id="zones"), _factory(id="paths")])

    host.device_loaded(stepping=None)

    assert [layer.calls for layer in host.layers] == [["attach", "device_loaded"]] * 2


def test_a_layer_attached_after_the_device_loads_catches_up(host, model):
    model.electrodes.set_electrodes_from_svg_file(str(BUNDLED_2X3))

    host.add_layers([_factory(id="zones")])

    assert host.layers[0].calls == ["attach", "device_loaded"]


class LayerContributingPlugin(Plugin):
    id = "test.layer_contributor"

    layers = List(contributes_to=DEVICE_VIEWER_LAYERS)

    def _layers_default(self):
        return [_factory(id="zones", section_title="Zones")]


def test_hot_load_and_unload_follow_the_extension_point(host, monkeypatch):
    # An envisage Application installs its preferences as the process-wide
    # default node; restore it so later PreferencesHelper tests don't share it.
    monkeypatch.setattr(package_globals, "_default_preferences", None)

    device_viewer_plugin = DeviceViewerPlugin()
    application = Application(plugins=[device_viewer_plugin])
    application.start()

    pane = HasTraits()
    pane.layer_host = host
    monkeypatch.setattr(device_viewer_plugin, "_live_dock_pane", lambda: pane)

    contributor = LayerContributingPlugin()
    application.add_plugin(contributor)

    assert [layer.id for layer in host.layers] == ["zones"]
    assert _box_titles(host) == ["A", "B", "Zones"]

    application.remove_plugin(contributor)

    assert host.layers == []
    assert _box_titles(host) == ["A", "B"]

    application.stop()
