# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT requests: power, gain and single acquire from the More Controls
pane, plus the PMT Capture pane's spot table and multi-spot capture.

The single acquire mirrors the vendor UI's macro: fluorescence LED off
(belt-and-braces — firmware dark-chambers it too) -> power on -> gain
-> acquire; the pane's Light setpoint is re-applied afterwards so the
Microdrop light state stays truthful.

The capture routine is the bench UI's capture session per spot: move ->
gain -> stream for the exposure -> stream stop -> CSV, with a teardown
that always reaches stream stop and power off. The proxy lock is taken
per command, not for the whole routine, so the status poll keeps the
status pane live over a multi-minute capture.
"""

# Standard library imports.
import json
import threading
import time
from datetime import datetime

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Bool, Dict, HasTraits, Instance, Int, Str, provides

# Microdrop package imports.
from microdrop_application.helpers import get_current_experiment_directory

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    PMT_ADC_FULL_SCALE,
    PMT_CAPTURE_SUBDIR,
    PMT_GAIN_BOUNDS,
    PMT_RF_OHMS,
    PMT_STREAM_AVG,
    PMT_STREAM_OSR,
    PMT_UPDATED,
    PMT_VREF_V,
    STREAM_DATA_CMD,
    STREAM_WAIT_SLICE_S,
    PmtCaptureRequest,
    pmt_capture_done_publisher,
    pmt_capture_progress_publisher,
    pmt_spots_updated_publisher,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..pmt_capture import (
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

    #: True from the start of a capture request to its done publish; a
    #: second request meanwhile is refused.
    _pmt_capturing = Bool(False)
    #: Set by PMT_CAPTURE_ABORT; the routine polls it between stream wait
    #: slices and before each spot.
    _pmt_capture_abort = Instance(threading.Event)
    #: slot -> position_um from the last spots read, for the CSV preamble.
    _pmt_spot_positions = Dict(Int, Int)

    def _publish_pmt(self, **payload):
        publish_message(topic=PMT_UPDATED, message=json.dumps(payload))

    # ------------------------------------------------------------------ #
    # More Controls pane: power / gain / single acquire                    #
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

    def on_pmt_acquire_request(self, message):
        if self.proxy is None:
            return
        gain = int(json.loads(str(message)).get("gain", -1))
        logger.info(
            f"Portable Dropbot PMT acquire started "
            f"(gain={'unchanged' if gain < 0 else gain})"
        )
        uart = self.proxy.uart
        self._publish_pmt(acquiring=True)
        # One lock for the whole macro so the status poll cannot
        # interleave; the fit takes ~10 s on a full buffer.
        with self._proxy_lock:
            try:
                self._proxy_call(
                    "PMT acquire: fluorescence LED off",
                    lambda: uart.setLEDIntensity(0, fluorescence=True),
                )
                self._proxy_call("PMT acquire: power on", lambda: uart.pmt_power(True))
                if gain >= 0:
                    self._proxy_call(
                        f"PMT acquire: gain {gain}", lambda: uart.pmt_set_gain(gain)
                    )
                ok, packets = self._proxy_call(
                    "PMT acquire", lambda: uart.pmt_acquire()
                )
            finally:
                # The macro forced the fluorescence LED off; put the
                # pane's Light setpoint back so state stays truthful.
                self._apply_light_intensity()
        self._publish_pmt(
            acquiring=False,
            acquired_packets=(int(packets) if ok and packets is not None else None),
        )
        logger.info(
            f"Portable Dropbot PMT acquire --> {packets if ok else 'FAILED'} packets"
        )

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

    # ------------------------------------------------------------------ #
    # PMT Capture pane: capture routine                                     #
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

    def _refuse_pmt_capture(self, error):
        """The done publish IS the ack; a refusal needs one too."""
        pmt_capture_done_publisher.publish(
            {
                "ok": False,
                "aborted": False,
                "directory": "",
                "results": [],
                "error": error,
            }
        )
        logger.warning(f"Portable Dropbot PMT capture refused: {error}")

    def on_pmt_capture_request(self, message):
        """Run the multi-spot capture inline; the done publish is the ack."""
        try:
            request = PmtCaptureRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_error("PMT capture", error)
            self._refuse_pmt_capture(str(error).splitlines()[0])
            return
        refusal = (
            "a PMT capture is already running"
            if self._pmt_capturing
            else "no spots ticked"
            if not request.entries
            else ""
        )
        if refusal:
            self._refuse_pmt_capture(refusal)
            return
        # Claim the routine right after the refusal check: the flag and
        # the abort event it guards must both be live before any I/O
        # below, or a second request racing in during that window would
        # drive the tube from two threads at once, and an abort arriving
        # in that same window would find no event to set.
        self._pmt_capturing = True
        self._pmt_capture_abort = threading.Event()
        try:
            directory = get_current_experiment_directory() / PMT_CAPTURE_SUBDIR
            directory.mkdir(parents=True, exist_ok=True)
        except Exception as error:
            self._pmt_capturing = False
            self._pmt_capture_abort = None
            logger.exception(f"Portable Dropbot PMT capture directory FAILED: {error}")
            self._refuse_pmt_capture(str(error) or repr(error))
            return
        logger.info(
            f"Portable Dropbot PMT capture started: "
            f"{len(request.entries)} spot(s) -> {directory}"
        )
        try:
            done = self._run_pmt_capture(
                request.entries, directory, self._pmt_capture_abort
            )
        finally:
            self._pmt_capturing = False
            self._pmt_capture_abort = None
        pmt_capture_done_publisher.publish(done)
        logger.info(
            f"Portable Dropbot PMT capture --> "
            f"{'ok' if done['ok'] else 'ABORTED' if done['aborted'] else 'FAILED'}"
            f"; files in {directory}"
        )

    def _run_pmt_capture(self, entries, directory, abort):
        """Capture every entry in order; never raises, always tears down."""
        total = len(entries)
        results = []
        aborted = False
        any_spot_failed = False
        request_error = ""
        # None until the proxy unpack below succeeds; the finally block
        # only tears down what was actually opened.
        uart = sig = None
        self._publish_pmt(acquiring=True)
        try:
            # self.proxy can vanish between the dispatcher's connection
            # check and here (a disconnect racing this worker thread);
            # that shows up as an AttributeError on the unpack below,
            # which the outer except turns into a failed-request ack
            # instead of an uncaught exception.
            if self.proxy is None:
                raise RuntimeError("PMT capture: no proxy connected")
            uart, sig, motor = self.proxy.uart, self.proxy.sig, self.proxy.motor
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

                def progress(stage, detail=""):
                    pmt_capture_progress_publisher.publish(
                        {
                            "index": index,
                            "total": total,
                            "slot": entry.slot,
                            "stage": stage,
                            "detail": detail,
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
                        lambda: motor.pmt_ctrl(entry.slot),
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
                    progress("stream")
                    # Subscribe before the start so no frame is missed.
                    uart.subscribe(STREAM_DATA_CMD, assembler.feed)
                    started = time.monotonic()
                    ok, reply = self._proxy_call(
                        "PMT capture: stream start",
                        lambda: sig.pmt_stream(1, PMT_STREAM_AVG, PMT_STREAM_OSR),
                    )
                    if not ok or reply is None:
                        raise RuntimeError("stream start: no reply (BUSY or timeout)")
                    deadline = started + entry.exposure_s
                    while time.monotonic() < deadline:
                        if abort.is_set():
                            aborted = True
                            break
                        time.sleep(STREAM_WAIT_SLICE_S)
                    self._proxy_call(
                        "PMT capture: stream stop", lambda: sig.pmt_stream(0, 0, 0)
                    )
                    uart.unsubscribe(STREAM_DATA_CMD)
                    saved = self._save_pmt_capture(
                        entry, assembler, directory, uids, started, aborted
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
                    uart.unsubscribe(STREAM_DATA_CMD)
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
                uart.unsubscribe(STREAM_DATA_CMD)
            self._apply_light_intensity()
            self._publish_pmt(acquiring=False)
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
            "error": request_error,
        }

    def _read_board_uids(self):
        """Both boards' factory UIDs for the CSV preamble; best-effort — a
        board answering with something unexpected never aborts the
        capture, it just leaves that UID "unavailable"."""
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

    def _save_pmt_capture(self, entry, assembler, directory, uids, started, aborted):
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
        period, source = calibrate_period(assembler, PMT_STREAM_AVG)
        meta = {
            "source": "Microdrop portable PMT capture",
            "taken": datetime.now().isoformat(timespec="seconds"),
            "slot": entry.slot,
            "position_um": self._pmt_spot_positions.get(entry.slot, ""),
            "gain": entry.gain,
            "exposure_s": entry.exposure_s,
            "avg": PMT_STREAM_AVG,
            "osr": PMT_STREAM_OSR,
            "adc_full_scale": PMT_ADC_FULL_SCALE,
            "vref_v": PMT_VREF_V,
            "rf_ohms": PMT_RF_OHMS,
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
        path = directory / capture_filename(entry.slot, entry.gain)
        write_capture_csv(path, samples, [i * period for i in sample_index], meta)
        result["csv_path"] = str(path)
        logger.info(
            f"Saved PMT spot {entry.slot} capture "
            f"({n} samples, {source} period) to {path}"
        )
        return result
