# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The fluorescence routine's pure helpers (reply bookkeeping, abort-aware
wait, LED scaling, frame tag) and the backend listener's dispatch of the
camera's reply signals. No hardware, no Redis, no Qt."""

# Standard library imports.
import threading
import time

# Enthought library imports.
from traits.api import Bool, Dict, HasTraits, List

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED,
    DEVICE_VIEWER_MEDIA_CAPTURED,
)
from portable_dropbot_controller.consts import FLUORESCENCE_LED_RAW_MAX, SET_VOLTAGE
from portable_dropbot_controller.fluorescence_capture import (
    PendingReplies,
    frame_description,
    led_raw,
    wait_with_abort,
)
from portable_dropbot_controller.portable_dropbot_controller_base import (
    PortableDropbotControllerBase,
)

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import TimestampedMessage


def test_pending_reply_round_trip():
    replies = PendingReplies()
    event = replies.expect("r1:0")

    assert replies.resolve("r1:0", {"ok": True}) is True
    assert event.is_set()
    assert replies.take("r1:0") == {"ok": True}
    # Taken means forgotten: a late duplicate is dropped.
    assert replies.resolve("r1:0", {"ok": False}) is False
    assert replies.take("r1:0") is None


def test_unexpected_reply_is_dropped():
    replies = PendingReplies()

    assert replies.resolve("nobody", {"ok": True}) is False
    assert replies.take("nobody") is None


def test_take_before_any_reply_is_none():
    replies = PendingReplies()
    replies.expect("r1:0")

    assert replies.take("r1:0") is None


def test_wait_returns_true_when_the_reply_arrives_from_another_thread():
    event, abort = threading.Event(), threading.Event()
    threading.Timer(0.05, event.set).start()

    assert wait_with_abort(event, abort, timeout_s=2.0) is True


def test_wait_times_out():
    event, abort = threading.Event(), threading.Event()
    started = time.monotonic()

    assert wait_with_abort(event, abort, timeout_s=0.1) is False
    assert not abort.is_set()
    assert time.monotonic() - started >= 0.1


def test_wait_returns_early_on_abort():
    event, abort = threading.Event(), threading.Event()
    threading.Timer(0.05, abort.set).start()
    started = time.monotonic()

    assert wait_with_abort(event, abort, timeout_s=5.0) is False
    assert abort.is_set()
    assert time.monotonic() - started < 1.0


def test_led_raw_scales_and_clamps():
    assert led_raw(0) == 0
    assert led_raw(100) == FLUORESCENCE_LED_RAW_MAX
    assert led_raw(50) == round(50 * FLUORESCENCE_LED_RAW_MAX / 100)
    assert led_raw(150) == FLUORESCENCE_LED_RAW_MAX
    assert led_raw(-5) == 0


def test_frame_description_tags_label_and_position():
    assert frame_description("step1.2-end", 3) == "flu_step1.2-end_f3"
    assert frame_description("manual", 1) == "flu_manual_f1"
    assert frame_description("", 2) == "flu_manual_f2"


class _Listener(HasTraits):
    """Stands in for the composed controller: just what the listener reads."""

    portable_dropbot_connection_active = Bool(False)
    timestamps = Dict()
    handled = List()

    def on_controls_applied_signal(self, message):
        self.handled.append(("controls_applied", str(message)))

    def on_set_voltage_request(self, message):
        self.handled.append(("set_voltage", str(message)))


def _dispatch(listener, topic, content, timestamp_ms):
    message = TimestampedMessage(content, timestamp_ms)
    PortableDropbotControllerBase.listener_actor_routine(listener, message, topic)


def test_camera_reply_signal_is_dispatched_while_disconnected():
    listener = _Listener()

    _dispatch(listener, DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED, '{"a": 1}', 1000.0)

    assert listener.handled == [("controls_applied", '{"a": 1}')]


def test_camera_reply_signals_skip_the_stale_filter():
    listener = _Listener()

    _dispatch(listener, DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED, "newer", 2000.0)
    _dispatch(listener, DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED, "older", 1000.0)

    assert [text for _name, text in listener.handled] == ["newer", "older"]


def test_signal_without_a_handler_is_ignored():
    listener = _Listener()

    _dispatch(listener, DEVICE_VIEWER_MEDIA_CAPTURED, "{}", 1000.0)

    assert listener.handled == []
    assert listener.timestamps == {}


def test_requests_are_still_denied_while_disconnected():
    listener = _Listener()

    _dispatch(listener, SET_VOLTAGE, "100", 1000.0)

    assert listener.handled == []

    listener.portable_dropbot_connection_active = True
    _dispatch(listener, SET_VOLTAGE, "100", 2000.0)

    assert listener.handled == [("set_voltage", "100")]
