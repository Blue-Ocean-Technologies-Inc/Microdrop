# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The device viewer pane builds its view on first show (#1087), while its
model — the loaded device, the messages announcing it, the listeners — is
in place from launch, so the other plugins cannot tell the view is unbuilt.

The real pane is mounted in a task window, behind another tab or in front,
with publishing recorded instead of sent and the camera panel stubbed.
"""

# Standard library imports.
import json
import sys
import time
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt import QtWidgets
from pyface.tasks.api import (
    DockPane,
    PaneItem,
    Tabbed,
    Task,
    TaskLayout,
    TaskPane,
    TaskWindow,
)
from traits.api import Any, Event, HasTraits, Instance

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    DEVICE_VIEWER_STATE_CHANGED,
    MASTER_SVG_FILE,
)
from pluggable_protocol_tree.models.display_state import ProtocolTreeDisplayMessage

# Microdrop utils imports.
from microdrop_utils.deferred_content import (
    CONTENT_BUILT,
    CONTENT_FAILED,
    CONTENT_LOADING,
)
from microdrop_utils.plugin_load_status import PluginLoadStatus

PANE_MODULE = "device_viewer.views.device_view_dock_pane"
CONTROLLER_MODULE = "device_viewer.controllers.device_viewer_message_controller"

DEVICE_VIEWER_ID = "device_viewer.dock_pane"
OTHER_ID = "test.other"

SMALL_DEVICE = MASTER_SVG_FILE.parent / "2x3device.svg"

#: Long enough for a paint, the pane's paced build and its sidebar sections.
SETTLE_MS = 1500


class FakeApplication(HasTraits):
    """The application surface the pane reads."""

    preferences_helper = Any()
    application_initialized = Event()
    extra_plugins_loaded = Event()
    plugin_load_status = Instance(PluginLoadStatus, ())

    def get_extensions(self, extension_id):
        return []

    def get_plugin(self, plugin_id):
        return None


class AppWindow(TaskWindow):
    application = Any()


class OtherPane(DockPane):
    id = OTHER_ID

    def create_contents(self, parent):
        return QtWidgets.QLabel("other", parent)


class CentralPane(TaskPane):
    def create(self, parent):
        self.control = QtWidgets.QLabel("central", parent)


class ProbeTask(Task):
    id = "test.task"

    def create_central_pane(self):
        return CentralPane()

    def create_dock_panes(self):
        from device_viewer.views.device_view_dock_pane import DeviceViewerDockPane

        return [DeviceViewerDockPane(task=self), OtherPane()]


class StubSignal:
    def __init__(self):
        self.emitted = []

    def emit(self, payload):
        self.emitted.append(payload)


def settle(ms=SETTLE_MS):
    deadline = time.perf_counter() + ms / 1000

    while time.perf_counter() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)


def open_window(active_tab):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    window = AppWindow(size=(1200, 800))
    window.application = FakeApplication(
        preferences_helper=SimpleNamespace(preferences=Preferences())
    )
    window.add_task(
        ProbeTask(
            default_layout=TaskLayout(
                left=Tabbed(
                    PaneItem(OTHER_ID),
                    PaneItem(DEVICE_VIEWER_ID),
                    active_tab=active_tab,
                )
            )
        )
    )
    window.open()
    settle()

    return window


def device_viewer(window):
    return window.get_dock_pane(DEVICE_VIEWER_ID)


def normalised(publishes):
    """The publishes, comparable from window to window: neighbour lists come
    from sets, ordered by string hashing."""
    result = []

    for topic, message in publishes:
        if topic == DEVICE_VIEWER_GEOMETRY_CHANGED:
            data = json.loads(message)
            data["neighbours"] = {
                electrode_id: sorted(adjacent)
                for electrode_id, adjacent in data["neighbours"].items()
            }
            message = json.dumps(data, sort_keys=True)

        result.append((topic, message))

    return result


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture
def published(monkeypatch):
    """Every message published, as (topic, message), instead of sent.

    The pane's module is imported first, so every module that publishes
    is loaded, and patched below."""
    from device_viewer.views import device_view_dock_pane  # noqa: F401

    from microdrop_utils import dramatiq_pub_sub_helpers

    original = dramatiq_pub_sub_helpers.publish_message
    records = []

    def record(message, topic, *args, **kwargs):
        records.append((topic, message))

    for module in list(sys.modules.values()):
        if getattr(module, "publish_message", None) is original:
            monkeypatch.setattr(module, "publish_message", record)

    return records


@pytest.fixture
def camera_widget(monkeypatch):
    """The camera panel's widget, stubbed: no camera is enumerated."""
    from device_viewer.models.camera import CameraModel
    from device_viewer.views.sidebar.section import SidebarSection

    class StubCameraSection(SidebarSection):
        camera_control_widget = Any()

    widget = SimpleNamespace(
        camera_model=CameraModel(),
        status_bar_manager=None,
        screen_capture_signal=StubSignal(),
    )

    monkeypatch.setattr(
        f"{PANE_MODULE}.build_camera_controls",
        lambda *args, **kwargs: StubCameraSection(
            title="Camera Controls",
            widget=QtWidgets.QLabel("camera"),
            camera_control_widget=widget,
        ),
    )

    return widget


@pytest.fixture
def no_listener_or_dialogs(monkeypatch):
    monkeypatch.setattr(
        f"{CONTROLLER_MODULE}.generate_class_method_dramatiq_listener_actor",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(f"{CONTROLLER_MODULE}.error", lambda *args, **kwargs: None)


@pytest.fixture
def builds(monkeypatch):
    """How many times the pane's contents were built."""
    from device_viewer.views.device_view_dock_pane import DeviceViewerDockPane

    counts = []
    create_contents = DeviceViewerDockPane.create_contents

    def counting(pane, parent):
        counts.append(pane)

        return create_contents(pane, parent)

    monkeypatch.setattr(DeviceViewerDockPane, "create_contents", counting)

    return counts


def _window_fixture(active_tab):
    window = open_window(active_tab)

    yield window

    window.close()
    settle(300)


@pytest.fixture
def behind(published, camera_widget, no_listener_or_dialogs, builds):
    """A window with the device viewer behind another tab."""
    yield from _window_fixture(OTHER_ID)


@pytest.fixture
def in_front(published, camera_widget, no_listener_or_dialogs, builds):
    """A window with the device viewer shown."""
    yield from _window_fixture(DEVICE_VIEWER_ID)


# --------------------------------------------------------------------------- #
# Behind a tab                                                                 #
# --------------------------------------------------------------------------- #
def test_behind_a_tab_the_model_is_in_place_and_the_view_is_not(behind, published):
    pane = device_viewer(behind)
    topics = [topic for topic, _message in published]

    assert pane.deferred_contents.state == CONTENT_LOADING
    assert not pane.device_view_built
    assert pane.current_electrode_layer is None
    assert pane.video_item is None
    assert not pane.sidebar_builder.started

    assert pane.device_loader.device_loaded
    assert pane.model.electrodes.electrode_ids_channels_map
    assert pane.zones_controller is not None
    assert pane.message_controller is not None

    assert topics.index(DEVICE_VIEWER_GEOMETRY_CHANGED) < topics.index(
        DEVICE_VIEWER_STATE_CHANGED
    )


def test_launch_publishes_the_same_whether_the_view_is_built_or_not(
    published, camera_widget, no_listener_or_dialogs, builds
):
    window = open_window(DEVICE_VIEWER_ID)
    built_at_launch = normalised(published)
    window.close()
    settle(300)

    published.clear()
    window = open_window(OTHER_ID)
    unbuilt_at_launch = normalised(published)

    device_viewer(window).control.raise_()
    settle()
    published_by_the_build = published[len(unbuilt_at_launch) :]
    window.close()
    settle(300)

    assert len(builds) == 2
    assert unbuilt_at_launch == built_at_launch
    assert published_by_the_build == []


def test_a_display_state_before_the_build_shows_once_built(behind):
    pane = device_viewer(behind)
    channels = pane.model.electrodes.electrode_ids_channels_map
    actuated, idle = sorted(channels)[:2]

    pane.message_controller._on_protocol_tree_display_state_triggered(
        ProtocolTreeDisplayMessage(
            electrodes=[actuated],
            routes=[],
            step_id="step-1",
            step_label="Wash",
            free_mode=False,
            editable=True,
        ).serialize()
    )

    assert pane.model.step_id == "step-1"
    assert pane.model.electrodes.actuated_channels == {channels[actuated]}
    assert pane.current_electrode_layer is None

    pane.control.raise_()
    settle()

    views = pane.current_electrode_layer.electrode_views

    assert pane.deferred_contents.state == CONTENT_BUILT
    assert views[actuated].color_stack != views[idle].color_stack


def test_a_halt_before_the_build_leaves_the_built_view_not_interactive(behind):
    pane = device_viewer(behind)

    pane.message_controller._on_halted_triggered(
        json.dumps({"name": "output-current-exceeded"})
    )
    settle(200)
    pane.control.raise_()
    settle()

    assert pane.device_view_built
    assert not pane.device_view.isInteractive()


def test_a_device_loaded_before_the_build_is_the_one_built(behind, published):
    pane = device_viewer(behind)
    published.clear()

    pane.message_controller._on_load_svg_request_triggered(str(SMALL_DEVICE))
    settle(300)

    (geometry,) = [
        message
        for topic, message in published
        if topic == DEVICE_VIEWER_GEOMETRY_CHANGED
    ]

    assert pane.svg_persistence.loaded_path == str(SMALL_DEVICE)
    assert set(json.loads(geometry)["id_to_channel"]) == set(
        pane.model.electrodes.electrodes
    )
    assert pane.current_electrode_layer is None

    pane.control.raise_()
    settle()

    assert set(pane.current_electrode_layer.electrode_views) == set(
        pane.model.electrodes.electrodes
    )


def test_a_device_loaded_once_built_rebuilds_the_view(in_front):
    pane = device_viewer(in_front)

    pane._set_device_view_from_svg(str(SMALL_DEVICE))

    assert set(pane.current_electrode_layer.electrode_views) == set(
        pane.model.electrodes.electrodes
    )


# --------------------------------------------------------------------------- #
# Camera requests                                                              #
# --------------------------------------------------------------------------- #
def test_a_camera_request_before_the_build_builds_the_pane_and_is_delivered(
    behind, camera_widget, builds
):
    pane = device_viewer(behind)

    pane.message_controller._on_screen_capture_triggered("")
    settle()

    assert len(builds) == 1
    assert pane.camera_control_widget is camera_widget
    assert camera_widget.screen_capture_signal.emitted == [None]

    # Built for the request, still behind its tab.
    assert not pane.showing_contents


def test_a_camera_request_is_answered_not_ok_when_the_pane_fails_to_build(
    published, camera_widget, no_listener_or_dialogs, builds, monkeypatch
):
    from device_viewer.views.device_view_dock_pane import DeviceViewerDockPane

    def broken(pane):
        raise RuntimeError("no view")

    replies = []
    monkeypatch.setattr(DeviceViewerDockPane, "_initialize_svg_view", broken)
    monkeypatch.setattr(
        f"{CONTROLLER_MODULE}.camera_source_selected_publisher",
        SimpleNamespace(publish=replies.append),
    )

    window = open_window(OTHER_ID)

    try:
        pane = device_viewer(window)
        pane.message_controller._on_select_source_triggered(
            json.dumps({"label": "Cam A", "request_id": "r1"})
        )
        settle()

        assert pane.deferred_contents.state == CONTENT_FAILED
        assert replies == [
            {
                "request_id": "r1",
                "label": "Cam A",
                "active": False,
                "ok": False,
                "error": "Device viewer camera: no view",
            }
        ]

    finally:
        window.close()
        settle(300)


# --------------------------------------------------------------------------- #
# Lifetime                                                                     #
# --------------------------------------------------------------------------- #
def test_shown_at_launch_it_builds_once(in_front, builds):
    pane = device_viewer(in_front)

    in_front.get_dock_pane(OTHER_ID).control.raise_()
    settle(300)
    pane.control.raise_()
    settle(300)

    assert len(builds) == 1
    assert pane.showing_contents
    assert pane.sidebar_builder.started


def test_raised_again_it_builds_once(behind, builds):

    for pane_id in (DEVICE_VIEWER_ID, OTHER_ID, DEVICE_VIEWER_ID):
        behind.get_dock_pane(pane_id).control.raise_()
        settle(500)

    assert len(builds) == 1


def test_a_pane_never_built_can_be_destroyed(behind, builds):
    pane = device_viewer(behind)

    pane.destroy()
    settle(300)

    assert builds == []
