# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Event-driven status (#1051): EVT_FIELDS frames merge into the last full
STATUS sample through the vendor's FieldsStatusModel, publishes are spaced
by the publish interval, a seq gap / stale stream asks for a STATUS read,
the stream is gated on MCU 1.0.1.33, and the monitor tick falls back to the
full poll without it. The STATUS tail carries heater channel 1 (#1082).
Hardware-free, no Redis."""

# Standard library imports.
import struct
import threading
from collections import namedtuple

# Third-party imports.
import pytest
from dropbot_portable import data_report

# Enthought library imports.
from traits.api import Any, List

# Microdrop package imports.
from portable_dropbot_controller.board_firmware import BoardFirmwareMixin
from portable_dropbot_controller.consts import (
    STATUS_EVENTS_PUBLISH_INTERVAL_S,
    STATUS_EVENTS_RESYNC_INTERVAL_S,
    STATUS_EVENTS_STALE_S,
)
from portable_dropbot_controller.status_events import (
    StatusEventsMixin,
    StatusEventStream,
    status_sample,
)

#: A full STATUS head, all zero, in the driver's engineering units.
BASE = {name: 0 for name in data_report.STATUS_FIELDS}

MotorStatus = namedtuple("MotorStatus", "rst cabin mag flu lpush rpush pmt")


def fields_frame(seq, **wire_values):
    """An EVT_FIELDS payload: [0x40][seq][n][n x {field id, u16 wire value}]."""
    body = b"".join(
        struct.pack(">BH", data_report.FIELD_IDS[name], value)
        for name, value in wire_values.items()
    )

    return struct.pack(">BBB", data_report.EVT_FIELDS, seq, len(wire_values)) + body


class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class _Uart:
    """Records the transport calls; echoes the event mask like the board."""

    def __init__(self, echo=True):
        self.echo = echo
        self.calls = []
        self.subscriber = None

    def subscribe(self, cmd, callback):
        self.calls.append(("subscribe", cmd))
        self.subscriber = callback

    def unsubscribe(self, cmd):
        self.calls.append(("unsubscribe", cmd))
        self.subscriber = None

    def set_report_interval(self, interval_ms):
        self.calls.append(("interval", interval_ms))

        return interval_ms

    def set_event_mask(self, mask):
        self.calls.append(("mask", mask))

        return mask if self.echo else None


class _Stream(StatusEventStream):
    """No publisher thread: the tests drive next_publish themselves."""

    def _start_publisher(self):
        pass


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def stream(clock):
    return _Stream(clock=clock)


def _started(stream):
    uart = _Uart()
    assert stream.start(uart)
    stream.note_status_sample(dict(BASE))

    return uart


# ---------------------------------------------------------------------- #
# status_sample: the STATUS head plus the driver's tail                    #
# ---------------------------------------------------------------------- #
def test_status_sample_adds_the_tail_with_heater_channel_1():
    tail = {
        "hv_setpoint": 120.0,
        "fault_flags": 2,
        "faults": ["output-current-exceeded"],
        "cur_temp1": 36.5,
        "target_temp1": 37.0,
        "out_power1": 12.5,
    }

    assert status_sample({"hv_vol": 119.5}, tail) == {"hv_vol": 119.5, **tail}


def test_status_sample_without_a_tail_is_the_head_alone():
    assert status_sample({"hv_vol": 119.5}, None) == {"hv_vol": 119.5}


# ---------------------------------------------------------------------- #
# Subscription                                                            #
# ---------------------------------------------------------------------- #
def test_start_subscribes_before_setting_the_event_mask(stream):
    uart = _Uart()

    assert stream.start(uart) is True
    assert stream.running is True
    assert [call[0] for call in uart.calls] == ["subscribe", "interval", "mask"]
    assert uart.calls[-1] == ("mask", data_report.EVT_FIELDS)


def test_a_board_that_does_not_echo_the_mask_leaves_the_poll(stream):
    uart = _Uart(echo=False)

    assert stream.start(uart) is False
    assert stream.running is False
    assert uart.subscriber is None


def test_stop_unsubscribes_and_turns_the_board_stream_off(stream):
    uart = _started(stream)

    stream.stop(disable_on_board=True)

    assert uart.subscriber is None
    assert uart.calls[-1] == ("mask", 0)
    assert stream.running is False

    # A late frame after the stop is ignored.
    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(1, hv_freq=1))
    assert stream.next_publish() == (None, None)


def test_a_lost_link_stop_sends_nothing_to_the_board(stream):
    uart = _started(stream)
    sent = len(uart.calls)

    stream.stop()

    assert uart.calls[sent:] == [("unsubscribe", data_report.CMD_DATA_REPORT)]


# ---------------------------------------------------------------------- #
# Merging                                                                 #
# ---------------------------------------------------------------------- #
def test_a_frame_merges_into_the_base_with_the_status_scaling(stream, clock):
    _started(stream)

    stream.on_data_report(
        data_report.CMD_DATA_REPORT,
        fields_frame(0, cur_temp=3712, cur_temp1=3650, fault_flags=2),
    )
    sample, wait_s = stream.next_publish()

    assert wait_s is None
    assert sample["cur_temp"] == 37.12
    assert sample["cur_temp1"] == 36.5
    assert sample["hv_vol"] == 0
    # The fault names follow the merged flags.
    assert sample["faults"] == data_report.fault_names(2)


def test_frames_before_a_base_publish_nothing_and_ask_for_a_read(clock):
    stream = _Stream(clock=clock)
    stream.start(_Uart())

    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(0, hv_freq=1))

    assert stream.next_publish() == (None, None)
    assert stream.status_read_due() is True

    stream.note_status_sample(dict(BASE))

    assert stream.status_read_due() is False


def test_other_data_reports_are_ignored(stream):
    _started(stream)
    status_payload = bytes(data_report.STATUS_LEN + 6)
    temperature_payload = bytes([data_report.EVT_TEMPERATURE]) + bytes(8)

    stream.on_data_report(data_report.CMD_DATA_REPORT, status_payload)
    stream.on_data_report(data_report.CMD_DATA_REPORT, temperature_payload)

    assert stream.next_publish() == (None, None)


def test_a_seq_gap_asks_for_one_status_read(stream):
    _started(stream)

    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(4, hv_freq=1))
    assert stream.status_read_due() is False

    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(6, hv_freq=2))
    assert stream.status_read_due() is True

    stream.note_status_sample(dict(BASE))
    assert stream.status_read_due() is False


# ---------------------------------------------------------------------- #
# Publish rate                                                            #
# ---------------------------------------------------------------------- #
def test_publishes_are_spaced_and_the_latest_sample_wins(stream, clock):
    _started(stream)

    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(0, hv_freq=1))
    first, _ = stream.next_publish()

    clock.now += STATUS_EVENTS_PUBLISH_INTERVAL_S / 4
    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(1, hv_freq=2))
    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(2, hv_freq=3))
    held, wait_s = stream.next_publish()

    clock.now += wait_s
    latest, _ = stream.next_publish()

    assert first["hv_freq"] == 1
    assert held is None
    assert wait_s == pytest.approx(STATUS_EVENTS_PUBLISH_INTERVAL_S * 3 / 4)
    assert latest["hv_freq"] == 3
    assert stream.next_publish() == (None, None)


def test_the_publisher_thread_publishes_a_merged_sample(clock):
    published, done = [], threading.Event()

    def publish(sample):
        published.append(sample)
        done.set()

    stream = StatusEventStream(clock=clock, publish=publish)
    uart = _Uart()
    stream.start(uart)
    stream.note_status_sample(dict(BASE))

    uart.subscriber(data_report.CMD_DATA_REPORT, fields_frame(0, hv_freq=10_000))

    try:
        assert done.wait(2.0)
    finally:
        stream.stop()

    assert published[0]["hv_freq"] == 10_000


# ---------------------------------------------------------------------- #
# Resync and stale stream                                                 #
# ---------------------------------------------------------------------- #
def test_a_full_read_falls_due_after_the_resync_interval(stream, clock):
    _started(stream)

    clock.now += STATUS_EVENTS_RESYNC_INTERVAL_S - 1
    stream.on_data_report(data_report.CMD_DATA_REPORT, fields_frame(0, hv_freq=1))
    assert stream.status_read_due() is False

    clock.now += 1
    assert stream.status_read_due() is True


def test_a_stale_stream_is_re_subscribed_once_per_resync_interval(stream, clock):
    uart = _started(stream)
    sent = len(uart.calls)

    clock.now += STATUS_EVENTS_STALE_S
    assert stream.status_read_due() is True
    # Too soon after the start's own subscription.
    assert stream.rearm_if_stale() is False

    clock.now += STATUS_EVENTS_RESYNC_INTERVAL_S
    assert stream.rearm_if_stale() is True
    assert stream.rearm_if_stale() is False
    assert uart.calls[sent:] == [
        ("interval", 1000),
        ("mask", data_report.EVT_FIELDS),
    ]


# ---------------------------------------------------------------------- #
# The monitor side: firmware gate and the tick's fallback                 #
# ---------------------------------------------------------------------- #
class _Session:
    def __init__(self):
        self.uart = _Uart()
        self.motor = self
        self.status_reads = 0

    def status(self):
        self.status_reads += 1

        return MotorStatus(0, 1, 0, 2, 1, 1, 0)


class _Monitor(StatusEventsMixin, BoardFirmwareMixin):
    proxy = Any()
    snapshots = List()
    motors = List()
    board_signals = List()

    def _proxy_call(self, context, call, serialize=True):
        return True, call()

    def _publish_status_snapshot(self):
        self.snapshots.append(True)
        self._note_status_sample(dict(BASE))

    def _publish_board_signal(self, sample):
        self.board_signals.append(sample)

    def _publish_motors(self, mechanisms=None, poll=True):
        self.motors.append(mechanisms)


def _monitor(mcu, clock):
    monitor = _Monitor(
        status_event_stream=_Stream(clock=clock),
        board_firmware_versions={"mcu": mcu},
    )
    monitor.proxy = _Session()

    return monitor


def test_firmware_before_1_0_1_33_stays_on_the_poll(clock):
    monitor = _monitor((1, 0, 1, 32), clock)

    monitor._start_status_events(monitor.proxy)
    monitor._refresh_status()
    monitor._refresh_status()

    assert monitor.proxy.uart.calls == []
    assert monitor.status_event_stream.running is False
    assert len(monitor.snapshots) == 2


def test_with_events_the_tick_reads_only_the_motor_board(clock):
    monitor = _monitor((1, 0, 1, 33), clock)

    monitor._start_status_events(monitor.proxy)
    monitor._publish_status_snapshot()
    monitor._refresh_status()

    assert monitor.status_event_stream.running is True
    assert len(monitor.snapshots) == 1
    assert monitor.motors == [MotorStatus(0, 1, 0, 2, 1, 1, 0)._asdict()]


def test_a_stale_stream_falls_back_to_the_full_poll(clock):
    monitor = _monitor((1, 0, 1, 33), clock)
    monitor._start_status_events(monitor.proxy)
    monitor._publish_status_snapshot()

    clock.now += STATUS_EVENTS_STALE_S
    monitor._refresh_status()

    assert len(monitor.snapshots) == 2
    assert monitor.motors == []


def test_the_stream_publishes_through_the_board_signal_path(clock):
    monitor = _monitor((1, 0, 1, 33), clock)

    monitor._start_status_events(monitor.proxy)

    assert monitor.status_event_stream.publish == monitor._publish_board_signal
    monitor._stop_status_events()
    assert monitor.status_event_stream.running is False
