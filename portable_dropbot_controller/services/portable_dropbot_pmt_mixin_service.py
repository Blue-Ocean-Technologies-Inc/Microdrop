# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT requests for the More Controls pane (power, gain) and the PMT
Capture pane (spot table, ADC query, multi-spot capture, live stream,
buffered acquire).

Three sessions share the tube and the ADC: the multi-spot capture, the
live stream, and the buffered acquire. Only one may run at a time — the
firmware itself enforces this (a stream/acquire start while another
session is open replies BUSY) — so `_pmt_claim` guards the check-and-set
of `_pmt_capturing` / `_pmt_streaming` / `_pmt_acquiring`; whichever flag
is already set gives the refusal its reason. A stream start received
while the stream is already running is not a new session, it is a live
avg/osr/gain update (no restart, no sample gap), so it is handled before
the claim is even consulted.

Each session runs on its own daemon thread, not inline in the Dramatiq
actor: a capture's 600 s exposure bound and the stream's open-ended
lifetime both run well past the actor's default time limit, and an
interrupted handler would leave the pane stuck mid-session with the
message retried against the board. The proxy lock is taken per command,
not for the whole session, so the status poll keeps the status pane live
throughout.

The ADC query (`spi_adc_diag`) shares the ADC bus with every session, so
it is refused while one is running; each session queries it for itself,
before power-on, and uses the answer for its own CSV meta.
"""

# Standard library imports.
import json
import threading
import time
from datetime import datetime

# Third-party imports.
from dropbot_portable.commands_generated import DroSIGCmd
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, Bool, Dict, HasTraits, Instance, Int, Str, provides

# Microdrop package imports.
from microdrop_application.helpers import get_current_experiment_directory

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    PMT_ACQUIRE_SAMPLE_RATE_HZ,
    PMT_ADC_FULL_SCALE,
    PMT_ADC_TYPES,
    PMT_CAPTURE_SUBDIR,
    PMT_GAIN_BOUNDS,
    PMT_PARK_LOCATION,
    PMT_SPOT_SLOTS,
    PMT_STREAM_AVG,
    PMT_STREAM_OSR,
    PMT_STREAM_PREEMPT_TIMEOUT_S,
    PMT_STREAM_PUBLISH_INTERVAL_S,
    PMT_STREAM_WAIT_SLICE_S,
    PMT_UPDATED,
    PMT_VREF_V,
    PmtAcquireRequest,
    PmtCaptureRequest,
    PmtStreamRequest,
    pmt_acquire_done_publisher,
    pmt_adc_updated_publisher,
    pmt_capture_done_publisher,
    pmt_capture_progress_publisher,
    pmt_spots_updated_publisher,
    pmt_stream_updated_publisher,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..pmt_capture import (
    LiveStreamBuffer,
    StreamAssembler,
    calibrate_period,
    capture_filename,
    capture_stats,
    decode_pmt_positions,
    write_capture_csv,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotPmtMixinService(HasTraits):
    id = Str("portable_dropbot_pmt_mixin_service")
    name = Str("Portable Dropbot PMT Mixin")

    #: True from the start of one PMT session to its done/updated publish;
    #: a request for a different session meanwhile is refused, and a
    #: second stream-start request is a live update instead (see module
    #: docstring).
    _pmt_capturing = Bool(False)
    _pmt_streaming = Bool(False)
    _pmt_acquiring = Bool(False)
    #: Set by PMT_CAPTURE_ABORT; the capture routine polls it between
    #: stream wait slices and before each spot.
    _pmt_capture_abort = Instance(threading.Event)
    #: Set by PMT_STREAM_STOP; the live stream's publish loop polls it
    #: instead of sleeping, so stop is immediate.
    _pmt_stream_stop_event = Instance(threading.Event)
    #: The three sessions' daemon threads — started and returned from
    #: immediately by their `on_..._request` so no Dramatiq actor time
    #: limit applies.
    _pmt_capture_thread = Instance(threading.Thread)
    _pmt_stream_thread = Instance(threading.Thread)
    _pmt_acquire_thread = Instance(threading.Thread)
    #: Serializes the read-check-set of the three `_pmt_*ing` flags (and
    #: each session's own event's creation), so two requests racing on
    #: different worker threads cannot both claim a session at once.
    #: `Instance(threading.Lock)` is rejected on Python 3.12 (the Pi's
    #: interpreter), hence `Any()` with a `_default` — see `_proxy_lock`
    #: in the controller base.
    _pmt_claim = Any()

    def __pmt_claim_default(self):
        return threading.Lock()

    #: slot -> position_um from the last spots read, for the CSV preamble.
    _pmt_spot_positions = Dict(Int, Int)

    #: The board's last-detected ADC type (spi_adc_diag's raw code) and
    #: full scale in counts; -1 means "not yet queried". Every session
    #: queries fresh at its own start, so this is only stale between
    #: sessions — used as the CSV meta while none is running.
    _pmt_adc_type = Int(-1)
    _pmt_adc_full_scale = Int(PMT_ADC_FULL_SCALE)

    #: avg/osr the running live stream was last told to use, reported
    #: back on every batch publish so the pane can show what is live.
    _pmt_stream_avg = Int(PMT_STREAM_AVG)
    _pmt_stream_osr = Int(PMT_STREAM_OSR)

    def _publish_pmt(self, **payload):
        publish_message(topic=PMT_UPDATED, message=json.dumps(payload))

    def _pmt_busy_reason(self):
        """Which session (if any) currently holds the shared claim."""

        if self._pmt_capturing:
            return "a PMT capture is running"

        if self._pmt_streaming:
            return "the live stream is running"

        if self._pmt_acquiring:
            return "a buffered acquire is running"

        return ""

    def _pmt_capture_directory(self):
        """The experiment's PMT capture folder, created on first use;
        shared by the multi-spot capture and the buffered acquire."""
        directory = get_current_experiment_directory() / PMT_CAPTURE_SUBDIR
        directory.mkdir(parents=True, exist_ok=True)

        return directory

    # ------------------------------------------------------------------ #
    # More Controls pane: power / gain                                     #
    # ------------------------------------------------------------------ #

    def on_pmt_power_request(self, message):
        on = str(message) == "True"
        ok, actual = self._proxy_call(
            "PMT power", lambda: self.proxy.uart.pmt_power(on)
        )

        if ok and actual is not None:
            self._publish_pmt(power=bool(actual))

        logger.info(
            f"Portable Dropbot PMT power --> "
            f"{'on' if on else 'off'}: "
            f"{'ok' if ok and actual is not None else 'FAILED'}"
        )

    def on_pmt_set_gain_request(self, message):
        gain = min(
            max(PMT_GAIN_BOUNDS[0], int(float(str(message)))), PMT_GAIN_BOUNDS[1]
        )

        ok, result = self._proxy_call(
            f"PMT gain {gain}", lambda: self.proxy.uart.pmt_set_gain(gain)
        )
        logger.info(
            f"Portable Dropbot PMT gain --> {gain}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    # ------------------------------------------------------------------ #
    # PMT Capture pane: ADC query                                          #
    # ------------------------------------------------------------------ #

    def _query_pmt_adc(self):
        """Query spi_adc_diag, remember the full scale for the caller's
        CSV meta, and publish PmtAdcUpdated. Must not race a running
        session — the ADC bus is shared — which is why every session
        calls this for itself before power-on rather than relying on a
        stale reading from an earlier query."""
        ok, reply = self._proxy_call(
            "PMT ADC diag", lambda: self.proxy.sig.spi_adc_diag()
        )

        if not ok or reply is None:
            pmt_adc_updated_publisher.publish(
                {"adc_type": -1, "name": "", "full_scale": 0, "error": "no reply"}
            )

            return

        adc_type = int(reply.adc_type)

        if adc_type == 0:
            name, full_scale = "none", 0
        else:
            name, full_scale = PMT_ADC_TYPES.get(adc_type, (f"unknown ({adc_type})", 0))

        self._pmt_adc_type = adc_type

        if full_scale:
            self._pmt_adc_full_scale = full_scale

        pmt_adc_updated_publisher.publish(
            {"adc_type": adc_type, "name": name, "full_scale": full_scale}
        )
        logger.info(f"Portable Dropbot PMT ADC --> {name}")

    def on_pmt_adc_query_request(self, message):
        """spi_adc_diag must not run during a stream/capture/acquire — it
        locks the ADC the same way the bench UI's query button does."""
        reason = self._pmt_busy_reason()

        if reason:
            pmt_adc_updated_publisher.publish(
                {"adc_type": -1, "name": "", "full_scale": 0, "error": reason}
            )

            return

        self._query_pmt_adc()

    # ------------------------------------------------------------------ #
    # PMT Capture pane: spot table                                          #
    # ------------------------------------------------------------------ #

    def on_pmt_spots_read_request(self, message):
        """Publish the configured slots of the motor board's PMT table."""
        ok, reply = self._proxy_call(
            "PMT spots read",
            lambda: self.proxy.uart.getBoardParameter("motor", "pmt_defaults"),
        )

        if not ok or not reply:
            logger.warning("Portable Dropbot PMT spots read FAILED")
            return

        try:
            positions = decode_pmt_positions(reply)
        except ValueError as error:
            self._publish_error("PMT spots read", error)
            return

        # A zero position is an unused slot (bench assumption, see #601).
        spots = [
            {"slot": i + 1, "position_um": p} for i, p in enumerate(positions) if p != 0
        ]

        if not spots:
            logger.warning(
                f"Portable Dropbot PMT position table has no non-zero slot: {positions}"
            )

        self._pmt_spot_positions = {s["slot"]: s["position_um"] for s in spots}
        pmt_spots_updated_publisher.publish({"spots": spots})
        logger.info(f"Portable Dropbot PMT spots --> {[s['slot'] for s in spots]}")

    def on_pmt_move_to_spot_request(self, message):
        """Move the PMT to a spot (0 = park). Refused while a capture runs —
        the capture routine owns the motor; a live stream or acquire keeps
        running, so the operator can watch the signal at the new spot."""
        spot = int(float(str(message)))

        if not 0 <= spot <= PMT_SPOT_SLOTS:
            logger.warning(f"PMT spot out of range: {spot}")

            return

        if self._pmt_capturing:
            logger.warning(f"PMT move to spot {spot} refused: a capture is running")

            return

        ok, location = self._proxy_call(
            f"PMT move to spot {spot}",
            lambda: self.proxy.motor.pmt_ctrl(spot + PMT_PARK_LOCATION),
        )
        logger.info(
            f"Portable Dropbot PMT --> spot {spot}: "
            f"{'ok' if ok and location is not None else 'FAILED'}"
        )

    # ------------------------------------------------------------------ #
    # PMT Capture pane: multi-spot capture routine                         #
    # ------------------------------------------------------------------ #

    def on_pmt_capture_abort_request(self, message):
        event = self._pmt_capture_abort

        if event is not None:
            event.set()
            logger.info("Portable Dropbot PMT capture: abort requested")
        else:
            logger.debug(
                "Portable Dropbot PMT capture abort ignored: no capture running"
            )

    def _refuse_pmt_capture(self, error, request_id="", label=""):
        """The done publish IS the ack; a refusal needs one too. request_id
        and label are echoed like a successful done, so a protocol step's
        wait_for_topics never hangs on a refusal it can't match."""
        pmt_capture_done_publisher.publish(
            {
                "ok": False,
                "aborted": False,
                "directory": "",
                "results": [],
                "request_id": request_id,
                "label": label,
                "error": error,
            }
        )
        logger.warning(f"Portable Dropbot PMT capture refused: {error}")

    def _pmt_capture_request_ids(self, message):
        """Best-effort request_id/label off a raw capture payload that
        failed full validation, so even a malformed request's refusal can
        still echo them; unreadable input reads as empty, per the module
        docstring's ack-always contract."""

        try:
            raw = json.loads(str(message))
        except Exception:
            return "", ""

        return str(raw.get("request_id", "")), str(raw.get("label", ""))

    def _claim_pmt_capture(self):
        """Try to claim the capture session; empty string means claimed.

        The read-check-set of the three `_pmt_*ing` flags and the abort
        event's creation is held under one lock so two requests racing in
        on different worker threads cannot both claim it — one would
        otherwise drive the tube from two threads at once, and an abort
        arriving in that window would find no event to set.
        """

        with self._pmt_claim:
            reason = self._pmt_busy_reason()

            if not reason:
                self._pmt_capturing = True
                self._pmt_capture_abort = threading.Event()

        return reason

    def _preempt_pmt_stream(self):
        """A protocol step's capture stops a running live stream instead of
        being refused: set its stop event and join its teardown thread,
        bounded by PMT_STREAM_PREEMPT_TIMEOUT_S, before the caller retries
        the claim. Never called while holding `_pmt_claim` — the stream's
        own teardown takes that same lock to clear `_pmt_streaming`."""
        stop_event = self._pmt_stream_stop_event
        thread = self._pmt_stream_thread

        if stop_event is not None:
            stop_event.set()

        if thread is not None:
            thread.join(timeout=PMT_STREAM_PREEMPT_TIMEOUT_S)

        logger.info("Portable Dropbot PMT capture: stopped the live stream to capture")

    def on_pmt_capture_request(self, message):
        """Validate, claim, and hand the routine to a daemon thread; the
        handler returns at once so no Dramatiq actor time limit applies
        to a multi-minute capture. The done publish, from that thread,
        is the ack."""
        try:
            request = PmtCaptureRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_error("PMT capture", error)
            request_id, label = self._pmt_capture_request_ids(message)
            self._refuse_pmt_capture(str(error).splitlines()[0], request_id, label)
            return

        if not request.entries:
            self._refuse_pmt_capture(
                "no spots ticked", request.request_id, request.label
            )
            return

        reason = self._claim_pmt_capture()

        # A step's capture stops a running stream instead of refusing —
        # only the stream blocker is ever preempted, never a capture or
        # acquire already in progress.
        stream_is_only_blocker = self._pmt_streaming and not (
            self._pmt_capturing or self._pmt_acquiring
        )

        if reason and request.stop_live_stream and stream_is_only_blocker:
            self._preempt_pmt_stream()
            reason = self._claim_pmt_capture()

        if reason:
            self._refuse_pmt_capture(reason, request.request_id, request.label)
            return

        abort = self._pmt_capture_abort

        try:
            directory = self._pmt_capture_directory()
        except Exception as error:
            # Broad except: any filesystem/preferences failure here must
            # become a refusal ack, never an unhandled exception.
            self._pmt_capturing = False
            self._pmt_capture_abort = None
            logger.exception(f"Portable Dropbot PMT capture directory FAILED: {error}")
            self._refuse_pmt_capture(
                str(error) or repr(error), request.request_id, request.label
            )
            return

        logger.info(
            f"Portable Dropbot PMT capture started: "
            f"{len(request.entries)} spot(s) -> {directory}"
        )
        self._pmt_capture_thread = threading.Thread(
            target=self._capture_and_finish,
            args=(request, directory, abort),
            daemon=True,
            name="pmt-capture",
        )
        self._pmt_capture_thread.start()

    def _capture_and_finish(self, request, directory, abort):
        """Thread body: run the routine, clear the claim, then publish and
        log the outcome — the part that used to run inline in the handler."""
        try:
            done = self._run_pmt_capture(request, directory, abort)
        finally:
            self._pmt_capturing = False
            self._pmt_capture_abort = None

        pmt_capture_done_publisher.publish(done)
        logger.info(
            f"Portable Dropbot PMT capture --> "
            f"{'ok' if done['ok'] else 'ABORTED' if done['aborted'] else 'FAILED'}"
            f"; files in {directory}"
        )

    def _run_pmt_capture(self, request, directory, abort):
        """Capture every entry in order; never raises, always tears down."""
        entries = request.entries
        total = len(entries)
        results = []
        aborted = False
        any_spot_failed = False
        request_error = ""
        # None until the proxy unpack below succeeds; the finally block
        # only tears down what was actually opened.
        uart = sig = None

        try:
            # Inside the try, not before it: a raise from the publish
            # itself must still reach the guaranteed teardown below.
            self._publish_pmt(acquiring=True)

            # self.proxy can vanish between the dispatcher's connection
            # check and here (a disconnect racing this worker thread);
            # that shows up as an AttributeError on the unpack below,
            # which the outer except turns into a failed-request ack
            # instead of an uncaught exception.
            if self.proxy is None:
                raise RuntimeError("PMT capture: no proxy connected")

            # pmt_stream/pmt_gain_set/pmt_power live only on the generated
            # sig/motor proxies, not the uart facade the single-acquire
            # path uses — one dialect per routine keeps the log readable.
            uart, sig, motor = self.proxy.uart, self.proxy.sig, self.proxy.motor
            self._query_pmt_adc()
            self._proxy_call(
                "PMT capture: fluorescence LED off",
                lambda: uart.setLEDIntensity(0, fluorescence=True),
            )
            ok, power = self._proxy_call(
                "PMT capture: power on", lambda: sig.pmt_power(1)
            )

            if not ok or power is None:
                raise RuntimeError("PMT power on: no reply")

            uids = self._read_board_uids()

            for index, entry in enumerate(entries):
                if abort.is_set():
                    aborted = True
                    break

                def progress(stage, detail="", exposure_s=0.0):
                    pmt_capture_progress_publisher.publish(
                        {
                            "index": index,
                            "total": total,
                            "slot": entry.slot,
                            "stage": stage,
                            "detail": detail,
                            "exposure_s": exposure_s,
                        }
                    )

                result = {
                    "slot": entry.slot,
                    "gain": entry.gain,
                    "exposure_s": entry.exposure_s,
                    "n_samples": 0,
                    "mean_counts": 0.0,
                    "sd_counts": 0.0,
                    "min_counts": 0,
                    "max_counts": 0,
                    "csv_path": "",
                    "error": "",
                }
                assembler = StreamAssembler()

                try:
                    progress("move")
                    ok, location = self._proxy_call(
                        f"PMT capture: move to spot {entry.slot}",
                        lambda: motor.pmt_ctrl(entry.slot + PMT_PARK_LOCATION),
                    )

                    if not ok or location is None:
                        raise RuntimeError(f"move to spot {entry.slot}: no reply")

                    progress("gain")
                    ok, set_ok = self._proxy_call(
                        f"PMT capture: gain {entry.gain}",
                        lambda: sig.pmt_gain_set(entry.gain),
                    )

                    if not ok or not set_ok:
                        raise RuntimeError(f"gain {entry.gain}: no reply")

                    progress("stream", exposure_s=entry.exposure_s)
                    # Subscribe before the start so no frame is missed.
                    uart.subscribe(DroSIGCmd.CMD_PMT_STREAM_DATA, assembler.feed)
                    started = time.monotonic()
                    ok, reply = self._proxy_call(
                        "PMT capture: stream start",
                        lambda: sig.pmt_stream(1, request.avg, request.osr),
                    )

                    if not ok or reply is None:
                        raise RuntimeError("stream start: no reply (BUSY or timeout)")

                    # started (for duration_s) is taken before the start
                    # command's round-trip; deadline is taken after the
                    # reply is checked so the real stream window is not
                    # short by that round-trip's latency.
                    deadline = time.monotonic() + entry.exposure_s
                    while time.monotonic() < deadline:
                        if abort.is_set():
                            aborted = True
                            break
                        time.sleep(PMT_STREAM_WAIT_SLICE_S)

                    self._proxy_call(
                        "PMT capture: stream stop", lambda: sig.pmt_stream(0, 0, 0)
                    )
                    uart.unsubscribe(DroSIGCmd.CMD_PMT_STREAM_DATA)
                    saved = self._save_pmt_capture(
                        entry, request, assembler, directory, uids, started, aborted
                    )
                    spot_failed = saved.pop("failed", False)
                    result.update(saved)

                    if spot_failed:
                        any_spot_failed = True
                        progress("failed", result["error"])
                    else:
                        progress("saved", result["csv_path"])
                except Exception as error:
                    # Per-spot failure: stop any stream this spot opened,
                    # record it, and move on to the next spot.
                    self._proxy_call(
                        "PMT capture: stream stop", lambda: sig.pmt_stream(0, 0, 0)
                    )
                    uart.unsubscribe(DroSIGCmd.CMD_PMT_STREAM_DATA)
                    any_spot_failed = True
                    result["error"] = str(error) or repr(error)
                    progress("failed", result["error"])
                    logger.exception(
                        f"Portable Dropbot PMT capture spot "
                        f"{entry.slot} FAILED: {error}"
                    )

                results.append(result)

                if aborted:
                    break
        except Exception as error:
            # Covers a vanished proxy, a power-on that never answered, or
            # any other request-level failure that is not one spot's own
            # — the whole request failed, but teardown below still runs.
            request_error = str(error) or repr(error)
            logger.exception(f"Portable Dropbot PMT capture FAILED: {error}")
        finally:
            # Guaranteed teardown; each step independent so one failure
            # cannot skip the next. Power off is the safety-relevant one.
            # uart/sig stay None only if the proxy vanished before either
            # was ever fetched, in which case there is nothing to tear
            # down on the board.
            if sig is not None:
                self._proxy_call(
                    "PMT capture: stream stop", lambda: sig.pmt_stream(0, 0, 0)
                )
                ok, off = self._proxy_call(
                    "PMT capture: power off", lambda: sig.pmt_power(0)
                )

                if not ok or off is None:
                    logger.error(
                        "Portable Dropbot PMT power OFF did not reach "
                        "the board — the tube may still be powered"
                    )

            if uart is not None:
                uart.unsubscribe(DroSIGCmd.CMD_PMT_STREAM_DATA)

            self._apply_light_intensity()
            self._publish_pmt(acquiring=False)

            if request.park_motor:
                ok, location = self._proxy_call(
                    "PMT capture: park",
                    lambda: self.proxy.motor.pmt_ctrl(PMT_PARK_LOCATION),
                )

                if not ok or location is None:
                    logger.error("Portable Dropbot PMT park after capture FAILED")

        complete = (
            not aborted
            and not request_error
            and len(results) == total
            and not any_spot_failed
        )

        return {
            "ok": complete,
            "aborted": aborted,
            "directory": str(directory),
            "results": results,
            "adc_full_scale": self._pmt_adc_full_scale,
            "rf_ohms": request.rf_ohms,
            "request_id": request.request_id,
            "label": request.label,
            "error": request_error,
        }

    def _read_board_uids(self):
        """Both boards' factory UIDs for the CSV preamble; best-effort — a
        board answering with something unexpected never aborts the
        capture, it just leaves that UID "unavailable".

        uart.read_uid() -> hex str, motor.read_uid() -> NamedTuple with
        raw bytes: the asymmetry is the driver's, not a bug here.
        """
        ok, uid = self._proxy_call(
            "PMT capture: signal UID", lambda: self.proxy.uart.read_uid()
        )
        ok_m, reply = self._proxy_call(
            "PMT capture: motor UID", lambda: self.proxy.motor.read_uid()
        )
        motor_uid = "unavailable"

        if ok_m and reply is not None:
            raw = getattr(reply, "uid", None)

            if raw is not None:
                try:
                    motor_uid = bytes(raw).hex()
                except (TypeError, ValueError) as error:
                    logger.warning(
                        f"Portable Dropbot PMT motor UID unreadable: {error}"
                    )

        return {
            "mcu_uid": uid if ok and uid else "unavailable",
            "motor_uid": motor_uid,
        }

    def _save_pmt_capture(
        self, entry, request, assembler, directory, uids, started, aborted
    ):
        """Stats + CSV for one spot; returns the result fields to merge.

        ``failed`` is a caller-only flag the per-spot loop pops before the
        dict joins ``results`` — it distinguishes "no data" from a caught
        exception whose ``str()`` happens to be empty, which a truthy
        check on ``error`` alone would miss.
        """
        samples, sample_index, _ = assembler.snapshot()
        n, mean, sd, lo, hi = capture_stats(samples)
        result = {
            "n_samples": n,
            "mean_counts": mean,
            "sd_counts": sd,
            "min_counts": lo,
            "max_counts": hi,
        }

        if not samples:
            result["error"] = "no stream frames received"
            result["failed"] = True
            return result

        period, source = calibrate_period(assembler, request.avg)
        meta = {
            "source": "Microdrop portable PMT capture",
            "taken": datetime.now().isoformat(timespec="seconds"),
            "slot": entry.slot,
            "motor_location": entry.slot + PMT_PARK_LOCATION,
            "position_um": self._pmt_spot_positions.get(entry.slot, ""),
            "gain": entry.gain,
            "exposure_s": entry.exposure_s,
            "avg": request.avg,
            "osr": request.osr,
            "adc_full_scale": self._pmt_adc_full_scale,
            "vref_v": PMT_VREF_V,
            "rf_ohms": request.rf_ohms,
            "request_id": request.request_id,
            "label": request.label,
            **uids,
            "sample_period_s": round(period, 6),
            "effective_rate_hz": round(1.0 / period, 2),
            "period_source": source,
            "samples_per_packet": assembler.samples_per_packet,
            "n_samples": n,
            "packets": assembler.packets,
            "duplicate_packets": assembler.duplicates,
            "duration_s": round(time.monotonic() - started, 3),
            "aborted": aborted,
            "error": "",
        }

        # A step's label is prefixed onto the CSV name (pmt_<label>_spot<n>_
        # ..._gain<g>.csv); a pane-initiated request leaves it empty, so
        # the name is unchanged from before labels existed.
        if request.label:
            kind = f"{request.label}_spot{entry.slot}"
        else:
            kind = f"spot{entry.slot}"

        path = directory / capture_filename(kind, entry.gain)
        write_capture_csv(path, samples, [i * period for i in sample_index], meta)
        result["csv_path"] = str(path)
        logger.info(
            f"Saved PMT spot {entry.slot} capture "
            f"({n} samples, {source} period) to {path}"
        )

        return result

    # ------------------------------------------------------------------ #
    # PMT Capture pane: live stream                                        #
    # ------------------------------------------------------------------ #

    def on_pmt_stream_start_request(self, message):
        """A start received while the stream is already running is a live
        avg/osr/gain update (no restart, no sample gap) — checked before
        the shared claim, which only serializes different SESSIONS."""

        try:
            request = PmtStreamRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_error("PMT stream start", error)
            pmt_stream_updated_publisher.publish(
                {"streaming": False, "error": str(error).splitlines()[0]}
            )

            return

        with self._pmt_claim:
            if self._pmt_streaming:
                stop = self._pmt_stream_stop_event

                # Held under the claim so a stream already tearing down
                # (stop set, see _run_pmt_stream) is never restarted by a
                # late update after its power-off.
                if stop is not None and not stop.is_set():
                    self._pmt_stream_live_update(request)

                return

            reason = self._pmt_busy_reason()

            if not reason:
                self._pmt_streaming = True
                self._pmt_stream_stop_event = threading.Event()

        if reason:
            pmt_stream_updated_publisher.publish({"streaming": False, "error": reason})

            return

        stop = self._pmt_stream_stop_event

        self._pmt_stream_thread = threading.Thread(
            target=self._run_pmt_stream,
            args=(request, stop),
            daemon=True,
            name="pmt-stream",
        )
        self._pmt_stream_thread.start()

    def _pmt_stream_live_update(self, request):
        """Push new avg/osr/gain to an already-running stream; the
        firmware applies them without restarting or dropping samples."""
        self._proxy_call(
            f"PMT stream: gain {request.gain}",
            lambda: self.proxy.sig.pmt_gain_set(request.gain),
        )
        self._proxy_call(
            "PMT stream: live update",
            lambda: self.proxy.sig.pmt_stream(1, request.avg, request.osr),
        )
        self._pmt_stream_avg, self._pmt_stream_osr = request.avg, request.osr

        pmt_stream_updated_publisher.publish(
            {"streaming": True, "avg": request.avg, "osr": request.osr}
        )
        logger.info(
            f"Portable Dropbot PMT stream live update --> "
            f"avg={request.avg}, osr={request.osr}, gain={request.gain}"
        )

    def on_pmt_stream_stop_request(self, message):
        event = self._pmt_stream_stop_event

        if event is not None:
            event.set()
            logger.info("Portable Dropbot PMT stream: stop requested")
        else:
            logger.debug("Portable Dropbot PMT stream stop ignored: no stream running")

    def _run_pmt_stream(self, request, stop):
        """Daemon-thread body of the live stream: mirrors the capture
        routine's opening (ADC query, LED off, power on, subscribe before
        the stream start) but loops publishing batches until
        PMT_STREAM_STOP instead of running one fixed exposure. Never
        raises; teardown below always runs."""
        buffer = LiveStreamBuffer()
        uart = sig = None
        error = ""

        try:
            if self.proxy is None:
                raise RuntimeError("PMT stream: no proxy connected")

            uart, sig = self.proxy.uart, self.proxy.sig
            self._query_pmt_adc()
            self._proxy_call(
                "PMT stream: fluorescence LED off",
                lambda: uart.setLEDIntensity(0, fluorescence=True),
            )
            ok, power = self._proxy_call(
                "PMT stream: power on", lambda: sig.pmt_power(1)
            )

            if not ok or power is None:
                raise RuntimeError("power on: no reply")

            self._publish_pmt(power=True)
            self._proxy_call(
                f"PMT stream: gain {request.gain}",
                lambda: sig.pmt_gain_set(request.gain),
            )
            self._pmt_stream_avg, self._pmt_stream_osr = request.avg, request.osr
            # Subscribe before the start so no frame is missed.
            uart.subscribe(DroSIGCmd.CMD_PMT_STREAM_DATA, buffer.feed)
            ok, reply = self._proxy_call(
                "PMT stream: start",
                lambda: sig.pmt_stream(1, request.avg, request.osr),
            )

            if not ok or reply is None:
                raise RuntimeError("stream start: no reply (BUSY or timeout)")

            pmt_stream_updated_publisher.publish(
                {"streaming": True, "avg": request.avg, "osr": request.osr}
            )

            while not stop.wait(PMT_STREAM_PUBLISH_INTERVAL_S):
                if self.proxy is None:
                    error = "disconnected"
                    break

                samples, packets = buffer.drain()

                if samples:
                    pmt_stream_updated_publisher.publish(
                        {
                            "streaming": True,
                            "avg": self._pmt_stream_avg,
                            "osr": self._pmt_stream_osr,
                            "samples": samples,
                            "packets": packets,
                        }
                    )
        except Exception as exc:
            error = str(exc) or repr(exc)
            logger.exception(f"Portable Dropbot PMT stream FAILED: {exc}")
        finally:
            # Mark the stream as stopping under the claim first, so no live
            # update can slip in between the stop below and the flag clear.
            with self._pmt_claim:
                stop.set()

            # Guaranteed teardown; each step independent so one failure
            # cannot skip the next.
            if sig is not None:
                self._proxy_call("PMT stream: stop", lambda: sig.pmt_stream(0, 0, 0))
                ok, off = self._proxy_call(
                    "PMT stream: power off", lambda: sig.pmt_power(0)
                )

                if not ok or off is None:
                    logger.error(
                        "Portable Dropbot PMT power OFF did not reach "
                        "the board — the tube may still be powered"
                    )

                self._publish_pmt(power=False)

            if uart is not None:
                uart.unsubscribe(DroSIGCmd.CMD_PMT_STREAM_DATA)

            self._apply_light_intensity()
            self._pmt_streaming = False
            self._pmt_stream_stop_event = None
            pmt_stream_updated_publisher.publish({"streaming": False, "error": error})

        logger.info(
            f"Portable Dropbot PMT stream --> "
            f"{'FAILED: ' + error if error else 'stopped'}"
        )

    # ------------------------------------------------------------------ #
    # PMT Capture pane: buffered acquire                                    #
    # ------------------------------------------------------------------ #

    def _refuse_pmt_acquire(self, gain, error):
        """The done publish IS the ack; a refusal needs one too."""
        pmt_acquire_done_publisher.publish({"ok": False, "gain": gain, "error": error})
        logger.warning(f"Portable Dropbot PMT acquire refused: {error}")

    def on_pmt_acquire_request(self, message):
        """Validate, claim, and hand the acquire to a daemon thread; the
        onboard fill plus upload run ~18-19 s, well past a request's
        expected latency. The done publish, from that thread, is the ack.
        The old `{"gain": g}` single-acquire payload still validates
        (rf_ohms has a default), so an unmigrated caller still works."""

        try:
            request = PmtAcquireRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_error("PMT acquire", error)
            self._refuse_pmt_acquire(-1, str(error).splitlines()[0])

            return

        with self._pmt_claim:
            reason = self._pmt_busy_reason()

            if not reason:
                self._pmt_acquiring = True

        if reason:
            self._refuse_pmt_acquire(request.gain, reason)

            return

        logger.info(f"Portable Dropbot PMT acquire started (gain={request.gain})")
        self._pmt_acquire_thread = threading.Thread(
            target=self._run_pmt_acquire,
            args=(request,),
            daemon=True,
            name="pmt-acquire",
        )
        self._pmt_acquire_thread.start()

    def _run_pmt_acquire(self, request):
        """Daemon-thread body of the buffered acquire; never raises. The
        deliberate change from the old single-lock macro is the teardown
        always powering off — that macro left the tube hot."""
        uart = sig = capture = None
        csv_path = ""
        error = ""
        n, mean, sd, lo, hi = 0, 0.0, 0.0, 0, 0
        packets_received = packets_expected = 0

        try:
            # Inside the try: a raise from the publish must still clear the
            # claim in the finally below.
            self._publish_pmt(acquiring=True)

            if self.proxy is None:
                raise RuntimeError("PMT acquire: no proxy connected")

            uart, sig = self.proxy.uart, self.proxy.sig
            self._query_pmt_adc()
            uids = self._read_board_uids()
            self._proxy_call(
                "PMT acquire: fluorescence LED off",
                lambda: uart.setLEDIntensity(0, fluorescence=True),
            )
            ok, power = self._proxy_call(
                "PMT acquire: power on", lambda: sig.pmt_power(1)
            )

            if not ok or power is None:
                raise RuntimeError("power on: no reply")

            ok, set_ok = self._proxy_call(
                f"PMT acquire: gain {request.gain}",
                lambda: sig.pmt_gain_set(request.gain),
            )

            if not ok or not set_ok:
                raise RuntimeError(f"gain {request.gain}: no reply")

            ok, capture = self._proxy_call(
                "PMT acquire: collect", lambda: uart.pmt_acquire_collect()
            )

            if not ok or capture is None:
                raise RuntimeError("collector declined: not connected")

            samples = list(capture.samples)
            n, mean, sd, lo, hi = capture_stats(samples)
            packets_received = capture.n_received
            packets_expected = capture.n_expected
            error = capture.error or ""

            if not error and capture.busy:
                error = "device busy (a stream or another acquire is open)"
            elif not error and not capture.complete:
                error = (
                    f"acquire incomplete: {packets_received}/{packets_expected} packets"
                )

            if samples:
                directory = self._pmt_capture_directory()
                path = directory / capture_filename("acquire", request.gain)
                meta = {
                    "source": "Microdrop portable PMT buffered acquire",
                    "taken": datetime.now().isoformat(timespec="seconds"),
                    "mode": "acquire",
                    "gain": request.gain,
                    "sample_rate_hz": PMT_ACQUIRE_SAMPLE_RATE_HZ,
                    "adc_type": self._pmt_adc_type,
                    "adc_full_scale": self._pmt_adc_full_scale,
                    "vref_v": PMT_VREF_V,
                    "rf_ohms": request.rf_ohms,
                    **uids,
                    "n_samples": n,
                    "packets_received": packets_received,
                    "packets_expected": packets_expected,
                    "missing_packets": len(capture.missing),
                    "aborted": capture.aborted,
                    "busy": capture.busy,
                    "error": error,
                }
                write_capture_csv(
                    path,
                    samples,
                    [i / PMT_ACQUIRE_SAMPLE_RATE_HZ for i in range(n)],
                    meta,
                )
                csv_path = str(path)
        except Exception as exc:
            error = str(exc) or repr(exc)
            logger.exception(f"Portable Dropbot PMT acquire FAILED: {exc}")
        finally:
            # Guaranteed teardown: power off is a deliberate behaviour
            # change from the old single-lock macro, which left the tube
            # powered after a single acquire.
            if sig is not None:
                ok, off = self._proxy_call(
                    "PMT acquire: power off", lambda: sig.pmt_power(0)
                )

                if not ok or off is None:
                    logger.error(
                        "Portable Dropbot PMT power OFF did not reach "
                        "the board — the tube may still be powered"
                    )

                self._publish_pmt(power=False)

            self._apply_light_intensity()
            self._publish_pmt(acquiring=False)
            self._pmt_acquiring = False

        ok = bool(csv_path) and capture is not None and capture.complete

        pmt_acquire_done_publisher.publish(
            {
                "ok": ok,
                "gain": request.gain,
                "n_samples": n,
                "mean_counts": mean,
                "sd_counts": sd,
                "min_counts": lo,
                "max_counts": hi,
                "packets_received": packets_received,
                "packets_expected": packets_expected,
                "adc_full_scale": self._pmt_adc_full_scale,
                "rf_ohms": request.rf_ohms,
                "csv_path": csv_path,
                "error": error,
            }
        )
        logger.info(
            f"Portable Dropbot PMT acquire --> "
            f"{'ok' if ok else 'FAILED'}: {n} samples, {csv_path or 'no CSV'}"
        )
