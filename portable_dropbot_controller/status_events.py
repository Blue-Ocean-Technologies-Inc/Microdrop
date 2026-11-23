# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Event-driven status (#1051). MCU firmware 1.0.1.33+ pushes change-only
EVT_FIELDS frames (DATA_REPORT 0x1205, mask bit 0x40): every STATUS field
that moved past its deadband, all of them every 5 s, and a seq that shows
a lost frame. The vendor's ``evt_fields.FieldsStatusModel`` merges them
into the last full STATUS sample; ``StatusEventStream`` feeds it and hands
each merged sample to a publisher thread, and ``StatusEventsMixin`` keeps
the STATUS poll as the resync and as the fallback for older firmware.
No Qt: unit-testable without hardware."""

# Standard library imports.
import threading
import time

# Third-party imports.
from dropbot_portable import data_report
from dropbot_portable.evt_fields import FieldsStatusModel, tail_from_sample

# Enthought library imports.
from traits.api import Any, Bool, Callable, Float, HasTraits, Instance

# Local imports.
from .consts import (
    STATUS_EVENTS_MIN_MCU_FIRMWARE,
    STATUS_EVENTS_PUBLISH_INTERVAL_S,
    STATUS_EVENTS_REPORT_INTERVAL_MS,
    STATUS_EVENTS_RESYNC_INTERVAL_S,
    STATUS_EVENTS_STALE_S,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def status_sample(signal, tail):
    """One full STATUS sample in the vendor status model's shape: the signal
    board's head fields plus the tail the driver captured from the same
    reply (hv_setpoint, fault_flags with their names, heater channel 1's
    temperature, target and power). MCU firmware before 1.0.1.30 sends no
    tail (None): the head alone."""
    sample = dict(signal)

    if isinstance(tail, dict):
        sample.update(tail_from_sample(tail))

    return sample


class StatusEventStream(HasTraits):
    """The EVT_FIELDS subscription of one connection and its status model.

    Frames arrive on the driver's reader thread (``on_data_report``), which
    only merges them under a short lock of its own: no driver call, no
    proxy lock, no publish. A publisher thread sends the latest merged
    sample at most once per ``publish_interval_s``."""

    #: Called on the publisher thread with each merged sample (head fields,
    #: tail fields and fault names) to publish.
    publish = Callable()

    #: Monotonic clock, injectable for tests.
    clock = Callable(time.monotonic)

    publish_interval_s = Float(STATUS_EVENTS_PUBLISH_INTERVAL_S)

    #: The vendor's model: the last full STATUS with every frame merged in.
    model = Instance(FieldsStatusModel, ())

    #: Subscribed, and the board echoed the event bit.
    running = Bool(False)

    #: The driver transport (``session.uart``) while running.
    _uart = Any()

    #: Guards the model and the bookkeeping below across the reader,
    #: publisher and monitor threads.
    _lock = Any()

    #: Per run: wakes the publisher, and ends it.
    _wake = Any()
    _stop = Any()

    #: The merged sample waiting for the publisher, or None.
    _pending = Any()

    _last_frame_t = Float()
    _last_base_t = Float()
    _last_arm_t = Float()
    _last_publish_t = Float(float("-inf"))

    #: A seq gap or a frame without a base asked for one STATUS read.
    _resync_requested = Bool(False)

    def __lock_default(self):
        return threading.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle (driver calls: run where a driver call may block)          #
    # ------------------------------------------------------------------ #
    def start(self, uart):
        """Subscribe to DATA_REPORT, then set the event mask to EVT_FIELDS;
        answers whether the board took it. The model starts empty: the next
        full STATUS read is its base."""
        self.stop()
        now = self.clock()

        with self._lock:
            self.model.reset()
            self._pending = None
            self._resync_requested = False
            self._last_frame_t = self._last_base_t = self._last_arm_t = now

        self._uart = uart
        self._wake, self._stop = threading.Event(), threading.Event()
        self.running = True
        self._start_publisher()

        # Subscribed before the mask, so the baseline frames the mask
        # change triggers are not missed (the vendor panel's order).
        uart.subscribe(data_report.CMD_DATA_REPORT, self.on_data_report)

        try:
            armed = self._arm(uart)
        except Exception:
            # Unhooked before the caller reports it (a dead link included).
            self.stop()
            raise

        if not armed:
            self.stop()

        return self.running

    def stop(self, disable_on_board=False):
        """Unsubscribe and end the publisher; with ``disable_on_board`` also
        turn the board's stream off (a deliberate close of a live link: the
        mask is RAM-only, so a lost link needs nothing)."""

        if not self.running:
            return

        uart, self._uart = self._uart, None
        self.running = False
        self._stop.set()
        self._wake.set()
        uart.unsubscribe(data_report.CMD_DATA_REPORT)

        with self._lock:
            self.model.reset()
            self._pending = None

        if disable_on_board:
            try:
                uart.set_event_mask(0)
            except Exception as exc:
                # Best effort: the port is being closed either way.
                logger.warning(f"Portable Dropbot event stream not turned off: {exc}")

    def rearm_if_stale(self):
        """Send the subscription again when no frame has arrived for
        STATUS_EVENTS_STALE_S (a board reset drops its RAM mask), at most
        once per STATUS_EVENTS_RESYNC_INTERVAL_S."""
        now = self.clock()

        with self._lock:
            due = (
                self.running
                and now - self._last_frame_t >= STATUS_EVENTS_STALE_S
                and now - self._last_arm_t >= STATUS_EVENTS_RESYNC_INTERVAL_S
            )

            if due:
                self._last_arm_t = now

        if due:
            logger.info("Portable Dropbot status events stale: re-subscribing.")
            self._arm(self._uart)

        return due

    @staticmethod
    def _arm(uart):
        """Interval first, so the first frames already come at that rate
        (the vendor hub's order), then the mask; True when the board echoed
        the event bit."""
        uart.set_report_interval(STATUS_EVENTS_REPORT_INTERVAL_MS)
        echoed = uart.set_event_mask(data_report.EVT_FIELDS)

        return echoed is not None and bool(echoed & data_report.EVT_FIELDS)

    # ------------------------------------------------------------------ #
    # Model feeds                                                          #
    # ------------------------------------------------------------------ #
    def on_data_report(self, cmd, data):
        """A DATA_REPORT frame, on the driver's reader thread. Only
        EVT_FIELDS frames count (a 36-byte+ payload is a full EVT_STATUS)."""
        raw = bytes(data)

        if (
            not raw
            or raw[0] != data_report.EVT_FIELDS
            or len(raw) >= data_report.STATUS_LEN
        ):
            return

        try:
            seq, fields = data_report.decode_fields_event(raw)
        except data_report.DataReportError as exc:
            logger.warning(f"Portable Dropbot status event dropped: {exc}")
            return

        with self._lock:
            if not self.running:
                return

            self._last_frame_t = self.clock()
            sample, resync = self.model.apply(seq, fields)
            self._resync_requested = self._resync_requested or resync

            if sample is not None:
                self._pending = sample

        if sample is not None:
            self._wake.set()

    def note_status_sample(self, sample):
        """A full STATUS read (``status_sample`` shape) is the new base; a
        pending resync is satisfied."""

        with self._lock:
            self.model.adopt_status(sample)
            self._last_base_t = self.clock()
            self._resync_requested = False

    def status_read_due(self):
        """Whether the monitor should read the full STATUS now: a resync
        was asked for, the last one is older than the resync interval, or
        the frames stopped."""
        now = self.clock()

        with self._lock:
            return (
                self._resync_requested
                or now - self._last_base_t >= STATUS_EVENTS_RESYNC_INTERVAL_S
                or now - self._last_frame_t >= STATUS_EVENTS_STALE_S
            )

    # ------------------------------------------------------------------ #
    # Publisher thread                                                     #
    # ------------------------------------------------------------------ #
    def next_publish(self):
        """``(sample, None)`` when a merged sample is due, ``(None, wait_s)``
        while the publish interval holds it back, ``(None, None)`` when
        nothing is pending. The sample's fault names follow its merged
        fault_flags."""

        with self._lock:
            if self._pending is None:
                return None, None

            now = self.clock()
            wait_s = self._last_publish_t + self.publish_interval_s - now

            if wait_s > 0:
                return None, wait_s

            sample, self._pending = self._pending, None
            self._last_publish_t = now

        sample.update(tail_from_sample(sample))

        return sample, None

    def _start_publisher(self):
        threading.Thread(
            target=self._run_publisher,
            args=(self._wake, self._stop),
            name="portable-status-events",
            daemon=True,
        ).start()

    def _run_publisher(self, wake, stop):
        while not stop.is_set():
            sample, wait_s = self.next_publish()

            if sample is not None:
                try:
                    self.publish(sample)
                except Exception:
                    # Broad by design: the publisher must outlive one bad
                    # sample.
                    logger.exception("Portable Dropbot status event not published")
            elif wait_s is None:
                wake.wait()
                wake.clear()
            else:
                stop.wait(wait_s)


class StatusEventsMixin(HasTraits):
    """The monitor's status refresh with events (MCU 1.0.1.33+) or without.
    Composes into the controller, which provides ``proxy``, ``_proxy_call``,
    ``_mcu_firmware_at_least``, ``_publish_status_snapshot``,
    ``_publish_board_signal`` and ``_publish_motors``."""

    #: The event stream of the live connection; idle on older firmware.
    status_event_stream = Instance(StatusEventStream, ())

    def _start_status_events(self, session):
        """Follow the change-only status events when the MCU firmware sends
        them; the STATUS poll stays otherwise."""

        if not self._mcu_firmware_at_least(STATUS_EVENTS_MIN_MCU_FIRMWARE):
            logger.info("MCU firmware predates status events: polling STATUS.")
            return

        stream = self.status_event_stream
        stream.publish = self._publish_board_signal
        ok, started = self._proxy_call(
            "status events start", lambda: stream.start(session.uart)
        )

        if ok and started:
            logger.info("Portable Dropbot status follows the event stream.")
        else:
            logger.warning("Status events refused by the board: polling STATUS.")

    def _stop_status_events(self, disable_on_board=False):
        self.status_event_stream.stop(disable_on_board)

    def _note_status_sample(self, sample):
        self.status_event_stream.note_status_sample(sample)

    def _refresh_status(self):
        """The monitor tick's refresh, proxy lock held. Without events, the
        full STATUS poll as before. With them, the full read only when a
        resync is due (a stale stream is also re-subscribed), else just the
        motor board's status: the events cover the signal board only."""
        stream = self.status_event_stream

        if not stream.running or stream.status_read_due():
            self._publish_status_snapshot()

            if stream.running:
                self._proxy_call("status events re-arm", stream.rearm_if_stale)

            return

        ok, reply = self._proxy_call(
            "motor status read", lambda: self.proxy.motor.status()
        )
        mechanisms = reply._asdict() if ok and reply is not None else {}
        self._publish_motors(mechanisms=mechanisms, poll=False)
