# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""CameraControlWidget.apply_select_source against a faked widget: a real
combo box wired the way a click is (index change -> controller select),
the real CameraController, and stub on/off and provider-feed hooks.
Offscreen Qt, no camera, no Redis."""

# Standard library imports.
from types import MethodType, SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtWidgets import QApplication, QComboBox

# Microdrop package imports.
from device_viewer.consts import CAMERA_FEED_START_TIMEOUT_MS, NO_CAMERA_LABEL
from device_viewer.controllers import camera_controller
from device_viewer.controllers.camera_controller import CameraController
from device_viewer.models.camera import CameraModel
from device_viewer.tests.test_camera_controller import Recorder, StubPreferences
from device_viewer.views.camera_control_view import widget as widget_module
from device_viewer.views.camera_control_view.widget import CameraControlWidget

ASI = "ASI: ZWO ASI183MM"


class _StubSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class _StubFeed:
    """A provider feed with the optional ``started`` signal."""

    def __init__(self):
        self.started = _StubSignal()


@pytest.fixture
def published(monkeypatch):
    replies, states = Recorder(), Recorder()
    monkeypatch.setattr(camera_controller, "camera_source_selected_publisher", replies)
    monkeypatch.setattr(camera_controller, "camera_state_publisher", states)

    return SimpleNamespace(replies=replies.calls, states=states.calls)


@pytest.fixture
def timers(monkeypatch):
    """(msec, callback) per QTimer.singleShot, run by the test."""
    scheduled = []
    monkeypatch.setattr(
        widget_module,
        "QTimer",
        SimpleNamespace(
            singleShot=lambda msec, callback: scheduled.append((msec, callback))
        ),
    )

    return scheduled


@pytest.fixture
def widget(published):
    """The surface apply_select_source touches, with the combo's index
    change selecting the source as on_camera_changed does. Turning the ASI
    entry on opens a new _StubFeed, as a provider source does."""
    QApplication.instance() or QApplication([])

    controller = CameraController(
        model=CameraModel(), preferences=StubPreferences(preferences=Preferences())
    )
    combo = QComboBox()
    combo.addItems(["Cam A", ASI, NO_CAMERA_LABEL])
    fake = SimpleNamespace(
        combo_cameras=combo,
        controller=controller,
        camera_model=controller.model,
        _active_feed=None,
        _pending_select_source=None,
    )

    def on_camera_changed(index):
        label = combo.itemText(index)
        fake._active_feed = None
        controller.select_source(
            "" if label == NO_CAMERA_LABEL else label, provider=label == ASI
        )

    def on_camera_active(active):
        if active and controller.model.provider_selected and fake._active_feed is None:
            fake._active_feed = _StubFeed()

        controller.model.camera_active = active

    combo.currentIndexChanged.connect(on_camera_changed)
    on_camera_changed(combo.currentIndex())

    fake.on_camera_active = on_camera_active
    fake.turn_off_camera = lambda: on_camera_active(False)

    for name in ("_await_feed_start", "_finish_pending_select_source"):
        setattr(fake, name, MethodType(getattr(CameraControlWidget, name), fake))

    return fake


def _apply(widget, label, active=None, request_id="r1"):
    CameraControlWidget.apply_select_source(
        widget, {"label": label, "active": active, "request_id": request_id}
    )


def test_selects_the_entry_and_turns_the_camera_on(widget, published):
    _apply(widget, "cam a", active=True)

    assert widget.combo_cameras.currentText() == "Cam A"
    assert published.replies == [
        {"request_id": "r1", "label": "Cam A", "ok": True, "error": "", "active": True}
    ]
    assert published.states[-1] == {
        "selected_camera": "Cam A",
        "active": True,
        "leased": False,
    }


def test_new_feed_reply_waits_for_started(widget, published, timers):
    _apply(widget, "asi: zwo asi183mm", active=True)

    assert published.replies == []
    assert timers[0][0] == CAMERA_FEED_START_TIMEOUT_MS

    widget._active_feed.started.emit()

    assert published.replies == [
        {"request_id": "r1", "label": ASI, "ok": True, "error": "", "active": True}
    ]

    # The timeout firing afterwards answers nothing twice.
    timers[0][1]()

    assert len(published.replies) == 1


def test_new_feed_reply_answers_ok_on_timeout(widget, published, timers):
    _apply(widget, ASI, active=True)
    timers[0][1]()

    assert published.replies[-1]["ok"] is True


def test_feed_error_while_waiting_fails_the_request(widget, published, timers):
    _apply(widget, ASI, active=True)

    CameraControlWidget._on_feed_error(widget, "Failed to open ASI camera")

    reply = published.replies[-1]

    assert reply["ok"] is False
    assert reply["error"] == (
        f"camera source {ASI!r} failed to start: Failed to open ASI camera"
    )
    assert reply["active"] is False


def test_running_feed_is_not_waited_on(widget, published, timers):
    _apply(widget, ASI, active=True)
    timers[0][1]()

    _apply(widget, ASI, active=True, request_id="r2")

    assert published.replies[-1]["request_id"] == "r2"
    assert len(timers) == 1


def test_a_later_camera_off_acts_on_the_same_state(widget, published):
    """The Video column's camera_active "false" lands on the same slot."""
    _apply(widget, "Cam A", active=True)

    widget.on_camera_active(False)

    assert published.states[-1]["active"] is False


def test_active_none_leaves_the_camera_as_it_is(widget, published):
    widget.on_camera_active(True)

    _apply(widget, "", request_id="restore")

    assert widget.combo_cameras.currentText() == NO_CAMERA_LABEL
    assert published.replies[-1]["ok"] is True
    assert published.replies[-1]["label"] == ""
    assert published.replies[-1]["active"] is True


def test_unknown_label_changes_nothing(widget, published):
    _apply(widget, "Cam Z", active=True)

    assert widget.combo_cameras.currentText() == "Cam A"
    assert published.replies[-1]["ok"] is False
    assert published.replies[-1]["label"] == "Cam Z"
    assert published.replies[-1]["active"] is False


def test_start_exception_is_answered_not_ok(widget, published):
    def failing_on(active):
        raise OSError("SDK not loaded")

    widget.on_camera_active = failing_on

    _apply(widget, ASI, active=True)

    reply = published.replies[-1]

    assert reply["ok"] is False
    assert reply["error"] == f"camera source {ASI!r} failed: SDK not loaded"
    assert reply["label"] == ASI
