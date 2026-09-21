# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fluorescence capture for the Fluorescence Capture pane and the
fluorescence_capture protocol column (#695).

Per entry, in list order: move the filter wheel, light the fluorescence
LED, have the frontend's camera take the entry's exposure and focus, then
have the device viewer save one still frame under the experiment's
captures/ folder. The camera lives in the frontend, so those two stages are
topic round trips — a CameraControlsRequest answered on
DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED, and a DEVICE_VIEWER_SCREEN_CAPTURE
answered on DEVICE_VIEWER_MEDIA_CAPTURED — whose replies reach this backend
through the controller's listener (on_controls_applied_signal /
on_media_captured_signal) and resolve the routine's waits by request_id.

The routine runs on a daemon thread, like the PMT capture: one filter move
may take 60 s, past a Dramatiq actor's time limit, and the reply handlers
need the worker threads free while the routine waits. Teardown always
restores the LED to the Light control's setpoint and returns the camera to
auto exposure and focus, whatever ended the run.
"""

# Standard library imports.
import json
import threading
import uuid
from pathlib import Path

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Instance, Str, observe, provides

# Microdrop package imports.
from device_viewer.consts import (
    CAPTURES_DIR_NAME,
    DEVICE_VIEWER_SCREEN_CAPTURE,
    camera_controls_publisher,
)
from microdrop_application.helpers import get_current_experiment_directory

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S,
    FLUORESCENCE_FRAME_TIMEOUT_S,
    FLUORESCENCE_SETTLE_S,
    FluorescenceCaptureRequest,
    fluorescence_capture_done_publisher,
    fluorescence_capture_progress_publisher,
)
from ..fluorescence_capture import (
    PendingReplies,
    frame_description,
    led_raw,
    wait_with_abort,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class _CaptureAborted(Exception):
    """The capture's abort event was set (abort request or disconnect)."""


@provides(IPortableDropbotControlMixinService)
class FluorescenceCaptureMixinService(HasTraits):
    id = Str("portable_dropbot_fluorescence_mixin_service")
    name = Str("Portable Dropbot Fluorescence Mixin")

    #: True from a capture's claim until just before its done publish, so a
    #: protocol step's back-to-back start/end captures never find a routine
    #: that has already finished still "busy".
    _fluorescence_capturing = Bool(False)
    #: Set by FLUORESCENCE_CAPTURE_ABORT or a disconnect; every stage checks
    #: it first and every wait returns early on it.
    _fluorescence_abort = Instance(threading.Event)
    #: The running capture's daemon thread (see the module docstring).
    _fluorescence_thread = Instance(threading.Thread)
    #: Serializes the busy check-and-set and the abort event's swap.
    #: `Instance(threading.Lock)` is rejected on the Pi's Python 3.12, hence
    #: `Any()` with a `_default`, as `_pmt_claim` in the PMT mixin.
    _fluorescence_claim = Any()

    def __fluorescence_claim_default(self):
        return threading.Lock()

    #: Camera-controls readbacks and saved frames the routine is waiting
    #: for, keyed by the per-entry reply id "<request id>:<index>".
    _fluorescence_camera_replies = Instance(PendingReplies, args=())
    _fluorescence_frame_replies = Instance(PendingReplies, args=())

    # ------------------------------------------------------------------ #
    # Requests                                                            #
    # ------------------------------------------------------------------ #

    def on_fluorescence_capture_request(self, message):
        """Validate, claim, and hand the routine to a daemon thread; the done
        publish, from that thread, is the ack."""
        try:
            request = FluorescenceCaptureRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_error("fluorescence capture", error)
            request_id, label = self._fluorescence_request_echo(message)
            self._refuse_fluorescence_capture(
                str(error).splitlines()[0], request_id, label
            )
            return

        if not request.entries:
            self._refuse_fluorescence_capture(
                "no filter positions ticked", request.request_id, request.label
            )
            return

        try:
            directory = request.directory or str(get_current_experiment_directory())
        except Exception as error:
            # Broad except: any preferences/Redis failure resolving the
            # experiment folder must become a refusal ack, never a hang.
            logger.error(f"Portable Dropbot fluorescence capture directory: {error}")
            self._refuse_fluorescence_capture(
                str(error) or repr(error), request.request_id, request.label
            )
            return

        with self._fluorescence_claim:
            busy = self._fluorescence_capturing

            if not busy:
                abort = threading.Event()
                self._fluorescence_abort = abort
                self._fluorescence_capturing = True

        if busy:
            self._refuse_fluorescence_capture("busy", request.request_id, request.label)
            return

        logger.info(
            f"Portable Dropbot fluorescence capture started: "
            f"{len(request.entries)} filter position(s) -> {directory}"
        )
        self._fluorescence_thread = threading.Thread(
            target=self._capture_fluorescence_and_finish,
            args=(request, directory, abort),
            daemon=True,
            name="fluorescence-capture",
        )
        self._fluorescence_thread.start()

    def on_fluorescence_capture_abort_request(self, message):
        abort = self._fluorescence_abort

        if abort is None:
            logger.debug(
                "Portable Dropbot fluorescence capture abort ignored: "
                "no capture running"
            )
            return

        abort.set()
        logger.info("Portable Dropbot fluorescence capture: abort requested")

    @observe("portable_dropbot_connection_active")
    def _abort_fluorescence_capture_on_disconnect(self, event):
        """Every disconnect path (the topic, a vanished serial link, the
        status watchdog) clears this flag; the monitor mixin's
        on_disconnected_signal does not chain, so this is the one hook
        they all share."""
        abort = self._fluorescence_abort

        if not event.new and abort is not None:
            abort.set()
            logger.warning(
                "Portable Dropbot disconnected: fluorescence capture aborted"
            )

    # ------------------------------------------------------------------ #
    # Camera replies (frontend signals, see the controller's listener)    #
    # ------------------------------------------------------------------ #

    def on_controls_applied_signal(self, message):
        """The camera's readback for a CameraControlsRequest; kept only when
        the routine is waiting for it (the teardown's auto request has no
        id and is never waited on)."""
        self._resolve_fluorescence_reply(self._fluorescence_camera_replies, message)

    def on_media_captured_signal(self, message):
        """A saved capture; kept only when it answers one of the routine's
        frame requests — button and protocol captures pass through."""
        self._resolve_fluorescence_reply(self._fluorescence_frame_replies, message)

    def _resolve_fluorescence_reply(self, replies, message):
        try:
            payload = json.loads(str(message))
        except ValueError:
            logger.warning(f"Unparseable camera reply ignored: {message!r}")
            return

        request_id = payload.get("request_id") if isinstance(payload, dict) else ""

        if request_id:
            replies.resolve(str(request_id), payload)

    # ------------------------------------------------------------------ #
    # The routine                                                         #
    # ------------------------------------------------------------------ #

    def _refuse_fluorescence_capture(self, error, request_id="", label=""):
        """The done publish IS the ack; a refusal needs one too, echoing
        request_id and label so a protocol step's wait still matches it."""
        fluorescence_capture_done_publisher.publish(
            {"request_id": request_id, "ok": False, "label": label, "error": error}
        )
        logger.warning(f"Portable Dropbot fluorescence capture refused: {error}")

    def _fluorescence_request_echo(self, message):
        """Best-effort request_id/label off a payload that failed validation,
        so even a malformed request's refusal can echo them."""
        try:
            raw = json.loads(str(message))
        except ValueError:
            return "", ""

        if not isinstance(raw, dict):
            return "", ""

        return str(raw.get("request_id", "")), str(raw.get("label", ""))

    def _capture_fluorescence_and_finish(self, request, directory, abort):
        """Thread body: run the routine, release the claim, then publish the
        outcome — released first, so whoever receives the done may ask for
        the next capture at once."""
        try:
            done = self._run_fluorescence_capture(request, directory, abort)
        finally:
            with self._fluorescence_claim:
                self._fluorescence_abort = None
                self._fluorescence_capturing = False

        fluorescence_capture_done_publisher.publish(done)
        logger.info(
            f"Portable Dropbot fluorescence capture --> "
            f"{'ok' if done['ok'] else 'FAILED: ' + done['error']}; "
            f"{len(done['paths'])} frame(s) in {done['directory']}"
        )

    def _run_fluorescence_capture(self, request, directory, abort):
        """Capture every entry in order; never raises, always tears down.
        Returns the FluorescenceCaptureDone payload."""
        # Replies are matched on "<id>:<index>"; a pane request may leave
        # request_id empty, so the routine mints its own id for them.
        reply_base = request.request_id or uuid.uuid4().hex
        total = len(request.entries)
        paths = []
        error = ""
        progress = self._fluorescence_progress(
            request, 0, total, request.entries[0].filter_position
        )

        try:
            for index, entry in enumerate(request.entries):
                progress = self._fluorescence_progress(
                    request, index, total, entry.filter_position
                )
                paths.append(
                    self._capture_fluorescence_entry(
                        request,
                        entry,
                        f"{reply_base}:{index}",
                        directory,
                        abort,
                        progress,
                    )
                )
        except _CaptureAborted:
            error = "aborted"
            logger.info("Portable Dropbot fluorescence capture aborted")
        except Exception as exc:
            # Any stage's failure ends the run; the frames already saved
            # stay listed in the done payload.
            error = str(exc) or repr(exc)
            logger.error(f"Portable Dropbot fluorescence capture FAILED: {error}")
        finally:
            progress("teardown")
            self._teardown_fluorescence_capture()

        return {
            "request_id": request.request_id,
            "ok": not error,
            "label": request.label,
            "directory": str(Path(directory) / CAPTURES_DIR_NAME),
            "paths": paths,
            "error": error,
        }

    def _capture_fluorescence_entry(
        self, request, entry, reply_id, directory, abort, progress
    ):
        """filter -> led -> camera -> frame for one entry; returns the saved
        frame's path, raises on the first failing stage."""
        position = entry.filter_position

        self._enter_fluorescence_stage(abort, progress, "filter")
        ok, moved = self._proxy_call(
            f"fluorescence capture: filter {position}",
            lambda: self.proxy.motor.fluorescence_ctrl(position),
        )

        if not ok and abort.is_set():
            # _proxy_call's own OSError handling already declared us
            # disconnected, which the connection observer turned into an
            # abort; that is the run's real outcome, not a stage failure.
            raise _CaptureAborted()

        if not ok or moved is None:
            # The vendor's alarm text (stall, move timeout, position unknown)
            # is already on ALARM_RAISED through the driver's on_alarm hook.
            raise RuntimeError(
                f"filter {position}: no reply (see the alarm; home the wheel "
                f"if its position is unknown)"
            )

        self._enter_fluorescence_stage(abort, progress, "led")
        raw = led_raw(entry.led_percent)
        ok, lit = self._proxy_call(
            f"fluorescence capture: LED {entry.led_percent} %",
            lambda: self.proxy.sig.fluorescence_ctrl(raw),
        )

        if not ok and abort.is_set():
            raise _CaptureAborted()

        if not ok or not lit:
            raise RuntimeError(f"LED {entry.led_percent} %: no reply")

        self._enter_fluorescence_stage(abort, progress, "camera")
        applied = self._await_fluorescence_reply(
            self._fluorescence_camera_replies,
            reply_id,
            lambda: camera_controls_publisher.publish(
                {
                    "request_id": reply_id,
                    "exposure_ms": entry.exposure_ms,
                    "focus_distance": entry.focus_distance,
                }
            ),
            FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S,
            abort,
            "camera",
        )

        if not applied.get("ok"):
            raise RuntimeError(
                f"camera: {applied.get('error') or 'controls not applied'}"
            )

        # The LED and the new exposure settle before the grab.
        if abort.wait(FLUORESCENCE_SETTLE_S):
            raise _CaptureAborted()

        self._enter_fluorescence_stage(abort, progress, "frame")
        frame_request = {
            "directory": directory,
            "step_description": frame_description(request.label, position),
            "show_dialog": False,
            "request_id": reply_id,
        }
        captured = self._await_fluorescence_reply(
            self._fluorescence_frame_replies,
            reply_id,
            lambda: publish_message(
                topic=DEVICE_VIEWER_SCREEN_CAPTURE, message=json.dumps(frame_request)
            ),
            FLUORESCENCE_FRAME_TIMEOUT_S,
            abort,
            "frame",
        )

        return str(captured.get("path", ""))

    def _enter_fluorescence_stage(self, abort, progress, stage):
        if abort.is_set():
            raise _CaptureAborted()

        progress(stage)

    def _await_fluorescence_reply(
        self, replies, reply_id, send, timeout_s, abort, stage
    ):
        """Register reply_id, send the request, and wait for its reply.
        Raises _CaptureAborted on abort, and TimeoutError naming the stage
        and the reply id when nothing matching arrives in time."""
        event = replies.expect(reply_id)

        try:
            send()
            arrived = wait_with_abort(event, abort, timeout_s)
        finally:
            reply = replies.take(reply_id)

        if arrived:
            return reply

        if abort.is_set():
            raise _CaptureAborted()

        raise TimeoutError(f"{stage}: no reply for {reply_id} within {timeout_s:g} s")

    def _fluorescence_progress(self, request, index, total, filter_position):
        """A publish(stage, detail="") bound to one entry. Progress is
        informational: a failed publish is logged, never allowed to fail
        or skip hardware work (the teardown publishes through it too)."""

        def publish(stage, detail=""):
            try:
                fluorescence_capture_progress_publisher.publish(
                    {
                        "request_id": request.request_id,
                        "index": index,
                        "total": total,
                        "filter_position": filter_position,
                        "stage": stage,
                        "detail": detail,
                    }
                )
            except Exception as error:
                logger.error(f"Fluorescence capture progress not published: {error}")

        return publish

    def _teardown_fluorescence_capture(self):
        """Guaranteed teardown, two independent blocks so one failure cannot
        skip the other. The camera's auto request is not waited on: nothing
        after teardown depends on its readback."""
        try:
            self._apply_light_intensity()
        except Exception as error:
            logger.error(f"Fluorescence capture: LED restore FAILED: {error}")

        try:
            camera_controls_publisher.publish({})
        except Exception as error:
            logger.error(f"Fluorescence capture: camera auto restore FAILED: {error}")
