# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free controller for the camera panel.

Owns the decisions the camera widget used to make inline: which source and
format to select, where captures and recordings are written, the recording
and capture bookkeeping (and what it publishes), exposure/focus requests
with their v4l2 fallbacks for the Portable Pi's GStreamer backend, the
focus row's live slider writes and one-shot autofocus sweep, the image
controls (brightness, contrast, ...) Qt has no API for, and the
camera's selection/on-off state with the replies to select_source
requests. The Qt side (QCamera, recorders, frame grabs, dialogs) stays in
the view, which calls in here and acts on the answers.
"""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from pyface.timer.api import CallbackTimer
from traits.api import Callable, Float, HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_application.helpers import get_current_experiment_directory

# Microdrop utils imports.
from microdrop_utils.camera_image_controls import (
    EXPOSURE_CONTROL,
    IMAGE_CONTROL_LABELS,
)
from microdrop_utils.libcamera_tuning import lens_focus_span
from microdrop_utils.system_config import is_rpi
from microdrop_utils.v4l2_fps_getter import (
    V4L2_EXPOSURE_AUTO,
    V4L2_EXPOSURE_AUTO_MANUAL,
    V4L2_EXPOSURE_AUTO_ON,
    V4L2_FOCUS_ABSOLUTE,
    V4L2_FOCUS_AUTO,
    get_v4l2_control,
    list_v4l2_controls,
    parse_v4l2_control_range,
    parse_v4l2_control_value,
    set_v4l2_controls,
)

# Local imports.
from ..consts import (
    AUTOFOCUS_TIMEOUT_S,
    CAPTURES_DIR_NAME,
    FALLBACK_PIXEL_FORMATS,
    FOCUS_WRITE_INTERVAL_S,
    LIBCAMERA_PIXEL_FORMAT,
    MIN_RECORDING_FPS,
    NO_CAMERA_LABEL,
    RECORDINGS_DIR_NAME,
    RPI_UNSUPPORTED_PIXEL_FORMATS,
    camera_controls_applied_publisher,
    camera_source_selected_publisher,
    camera_state_publisher,
    device_viewer_recording_state_publisher,
    media_capture_event_model,
    recording_state_model,
)
from ..interfaces.i_camera_device import ICameraDevice
from ..models.autofocus import ContrastAutofocus, laplacian_variance
from ..models.camera import CameraImageSetting, CameraModel
from ..models.media import MediaType
from ..services.media_capture_cache import _cache_media_capture
from ..utils.capture import media_filename
from ..utils.latest_value_throttle import LatestValueThrottle

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _pixel_format_name(pixel_format):
    """Qt's pixel format name without its prefixes, upper-cased:
    "PixelFormat.Format_YV12" and "Format_YV12" are both "YV12"."""
    name = str(pixel_format).rsplit(".", 1)[-1].upper()

    return name.removeprefix("FORMAT_")


class CameraController(HasTraits):
    """Camera-panel decisions and publishing; see the module docstring."""

    #: Qt-free panel state.
    model = Instance(CameraModel, ())

    #: The camera preferences (selected camera, resolution, recording).
    preferences = Instance(PreferencesHelper)

    #: The live camera.
    camera = Instance(ICameraDevice)

    #: Switch the camera on — the view's routine, which also syncs its
    #: toggle button; set_controls turns an idle camera on first.
    turn_camera_on = Callable()

    #: Coalesces the focus slider's drag into focus writes.
    focus_edits = Instance(LatestValueThrottle)

    #: The one-shot autofocus sweep, fed live frames while it runs.
    autofocus = Instance(ContrastAutofocus, ())

    #: Cancels a sweep that stops getting frames.
    _autofocus_timeout = Instance(CallbackTimer)

    #: monotonic() time the running sweep started.
    _autofocus_started = Float()

    def _focus_edits_default(self):
        return LatestValueThrottle(
            interval=FOCUS_WRITE_INTERVAL_S, callback=self._write_focus
        )

    def __autofocus_timeout_default(self):
        return CallbackTimer(
            interval=AUTOFOCUS_TIMEOUT_S, callback=self._autofocus_timed_out
        )

    @observe("model:camera_active")
    def _remember_camera_state(self, event):
        self.preferences.camera_state = event.new

    @observe("model:selected_camera, model:camera_active, model:camera_leased")
    def _publish_camera_state(self, event=None):
        """Publish the selection, on/off and lease state on
        DEVICE_VIEWER_CAMERA_STATE — on every change, including the panel's
        first source selection."""
        camera_state_publisher.publish(
            {
                "selected_camera": self.model.selected_camera,
                "active": self.model.camera_active,
                "leased": self.model.camera_leased,
            }
        )

    # ------------------------------------------------------------------ #
    # Source and format selection                                          #
    # ------------------------------------------------------------------ #
    def choose_camera_index(self, camera_labels, provider_labels, current_label=""):
        """Index of the source to select after (re-)enumerating sources.

        The listing is ``camera_labels``, then ``provider_labels``, then
        "<No Camera>". The preferred camera (or ``current_label``) wins when
        still present; otherwise its stale resolution is dropped and the
        first entry is selected.
        """
        preferred = self.preferences.selected_camera or current_label

        if not preferred:
            return 0

        if preferred in camera_labels:
            return camera_labels.index(preferred)

        if preferred in provider_labels:
            return len(camera_labels) + provider_labels.index(preferred)

        # The resolution belonged to the missing camera.
        logger.warning(
            f"Preferred camera '{preferred}' not found. "
            f"Falling back to first available camera."
        )
        self.preferences.resolution = ""

        return 0

    def select_source(
        self,
        label,
        remembered_as="",
        provider=False,
        v4l2_device_path=None,
        v4l2_focus_device_path=None,
        v4l2_focus_lens_map=(),
    ):
        """Record the selected source.

        ``remembered_as`` is saved as the preferred camera — a provider's
        label, a QCamera's Qt description; empty for "<No Camera>", which
        leaves the preference alone. ``v4l2_device_path`` is the camera's
        ``/dev/videoN`` node, ``v4l2_focus_device_path`` the node its focus
        fallback drives and ``v4l2_focus_lens_map`` that lens's calibration
        (see CameraModel).
        """
        self.cancel_autofocus("camera changed")
        self.focus_edits.cancel()

        if remembered_as:
            self.preferences.selected_camera = remembered_as

        self.model.selected_camera = label
        self.model.provider_selected = provider
        self.model.v4l2_device_path = v4l2_device_path

        # Before the focus device, whose change reads the focus span.
        self.model.v4l2_focus_lens_map = list(v4l2_focus_lens_map)
        self.model.v4l2_focus_device_path = v4l2_focus_device_path

        self.refresh_focus()
        self.refresh_image_settings()

    @staticmethod
    def match_source_label(labels, label):
        """Index in ``labels`` (the dropdown, in order) of the entry ``label``
        names, or None: the exact label, else a case-insensitive match; ""
        names "<No Camera>", which CameraState reports as ""."""
        wanted = label or NO_CAMERA_LABEL

        if wanted in labels:
            return labels.index(wanted)

        folded = [entry.casefold() for entry in labels]

        if wanted.casefold() in folded:
            return folded.index(wanted.casefold())

        return None

    def find_requested_source(self, request, labels):
        """Index in ``labels`` of the entry a CameraSelectSourceRequest dict
        names; when it names none, answer the request ok=False and return
        None."""
        index = self.match_source_label(labels, request["label"])

        if index is None:
            self._answer_select_source(
                request,
                request["label"],
                f"unknown camera source {request['label']!r} "
                f"(available: {', '.join(labels)})",
            )

        return index

    def source_selected(self, request, error=""):
        """Answer a CameraSelectSourceRequest dict whose source is now
        selected: ok unless ``error`` or the camera was asked on and is
        not."""
        label = self.model.selected_camera

        if not error and request["active"] and not self.model.camera_active:
            if not label:
                error = "no camera source is selected"
            elif self.model.provider_selected and self.model.feed_error:
                error = (
                    f"camera source {label!r} failed to start: {self.model.feed_error}"
                )
            else:
                error = f"camera source {label!r} failed to start (see the log)"

        self._answer_select_source(request, label, error)

    def _answer_select_source(self, request, label, error):
        """Publish the CameraSourceSelected reply, then the camera state, so
        a requester also learns the state it may restore later."""
        if error:
            logger.error(f"Camera select_source not applied: {error}")

        camera_source_selected_publisher.publish(
            {
                "request_id": request["request_id"],
                "label": label,
                "ok": not error,
                "error": error,
                "active": self.model.camera_active,
            }
        )

        self._publish_camera_state()

    def strict_format_mode(self, allow_strict_mode=True, libcamera=False):
        """Whether only the preferred pixel format may be offered: under the
        strict-format preference, unless lifted by ``allow_strict_mode`` or
        for a libcamera source, which never offers the preferred JPEG."""
        return (
            self.preferences.strict_video_format and allow_strict_mode and not libcamera
        )

    def rank_formats(self, formats, allow_strict_mode=True, libcamera=False):
        """Indices of the formats to offer, best first, one per resolution.

        ``formats`` holds ``(width, height, pixel_format, frame_rate)`` per
        camera format. Larger resolutions come first; within a resolution
        the preferred pixel format wins, then the higher frame rate, then
        FALLBACK_PIXEL_FORMATS in order. Under strict_format_mode only the
        preferred pixel format is offered. A ``libcamera`` source prefers
        LIBCAMERA_PIXEL_FORMAT instead, and a Raspberry Pi never offers
        RPI_UNSUPPORTED_PIXEL_FORMATS.
        """
        if libcamera:
            preferred_format = LIBCAMERA_PIXEL_FORMAT
        else:
            preferred_format = self.preferences.preferred_video_format.upper()

        strict_mode = self.strict_format_mode(allow_strict_mode, libcamera)
        unsupported_formats = RPI_UNSUPPORTED_PIXEL_FORMATS if is_rpi() else ()

        def sort_key(index):
            width, height, pixel_format, frame_rate = formats[index]
            name = _pixel_format_name(pixel_format)

            if name in FALLBACK_PIXEL_FORMATS:
                fallback_rank = FALLBACK_PIXEL_FORMATS.index(name)
            else:
                fallback_rank = len(FALLBACK_PIXEL_FORMATS)

            return (
                -width,
                -height,
                name != preferred_format,
                -frame_rate,
                fallback_rank,
                name,
            )

        ranked = []
        seen_resolutions = set()

        for index in sorted(range(len(formats)), key=sort_key):
            width, height, pixel_format, _ = formats[index]
            name = _pixel_format_name(pixel_format)

            if name in unsupported_formats:
                continue

            if strict_mode and name != preferred_format:
                continue

            if (width, height) in seen_resolutions:
                continue

            seen_resolutions.add((width, height))
            ranked.append(index)

        return ranked

    def choose_resolution_index(self, labels):
        """Index of the saved resolution in ``labels``, else the middle one."""
        saved_resolution = self.preferences.resolution

        if saved_resolution and saved_resolution in labels:
            return labels.index(saved_resolution)

        if saved_resolution:
            logger.warning(
                f"Saved resolution '{saved_resolution}' not available. "
                f"Falling back to default (middle resolution)."
            )

        return len(labels) // 2

    def select_resolution(self, label, width, height, frame_rate):
        """Record the selected camera format."""
        self.preferences.resolution = label
        self.model.resolution = (width, height)
        self.model.frame_rate = frame_rate

    # ------------------------------------------------------------------ #
    # Image capture                                                        #
    # ------------------------------------------------------------------ #
    def capture_target(self, capture_data=None):
        """Where a capture goes and how it is announced.

        ``capture_data`` is a DEVICE_VIEWER_SCREEN_CAPTURE payload (or None
        for the capture button). Returns ``(save_path, show_status_message,
        request_id)``.
        """
        capture_data = capture_data if isinstance(capture_data, dict) else {}

        filename = media_filename(
            capture_data.get("step_description"), capture_data.get("step_id"), ".png"
        )
        save_path = (
            self._media_directory(capture_data.get("directory"))
            / CAPTURES_DIR_NAME
            / filename
        )

        return (
            save_path,
            capture_data.get("show_status_message", True),
            str(capture_data.get("request_id", "")),
        )

    def image_saved(self, saved_path, request_id=""):
        """Cache and announce a capture that is on disk."""
        _cache_media_capture(MediaType.IMAGE, saved_path, request_id)
        media_capture_event_model.captured = saved_path
        self.model.last_capture_path = saved_path

    # ------------------------------------------------------------------ #
    # Recording                                                            #
    # ------------------------------------------------------------------ #
    def recording_frame_rate_supported(self, frame_rate):
        return frame_rate >= MIN_RECORDING_FPS

    def prepare_recording(
        self,
        directory=None,
        step_description=None,
        step_id=None,
        show_status_message=True,
        camera_was_on=True,
    ):
        """Create the recording's folder and return its file path."""
        filename = media_filename(
            step_description, step_id, self.preferences.recording_file_extension()
        )
        path = self._media_directory(directory) / RECORDINGS_DIR_NAME / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        recording = self.model.recording
        recording.camera_was_on = camera_was_on
        recording.show_status_message = show_status_message
        recording.output_path = str(path)

        return str(path)

    def recording_started(self):
        self._publish_recording_state(True)

    def recording_ended(self):
        """Announce the end of a recording (finished or failed); returns
        whether the camera should now be switched back off."""
        self._publish_recording_state(False)

        return not self.model.recording.camera_was_on

    def _publish_recording_state(self, active):
        device_viewer_recording_state_publisher.publish(state=active)
        recording_state_model.recording = active
        self.model.recording.active = active

    @staticmethod
    def _media_directory(directory):
        return Path(directory) if directory else get_current_experiment_directory()

    # ------------------------------------------------------------------ #
    # Exposure / focus (CameraControlsRequest)                             #
    # ------------------------------------------------------------------ #
    def apply_camera_controls(self, request):
        """Apply a CameraControlsRequest dict to the camera (turning it on
        first if it is off) and answer with the camera's readback on
        DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED. Manual focus falls back to
        v4l2-ctl on cameras where Qt cannot drive it (see _apply_focus). A
        provider feed (no QCamera) or an unsupported mode answers ok=False
        rather than raising."""
        request = request if isinstance(request, dict) else {}
        reply = {"request_id": str(request.get("request_id", "")), "ok": False}

        if self.model.provider_feed_active or not self.camera.has_camera():
            reply["error"] = "no QCamera is selected"
            camera_controls_applied_publisher.publish(reply)

            return

        if not self.camera.is_active():
            self.turn_camera_on()

        self.cancel_autofocus("focus set by a camera controls request")
        self.focus_edits.cancel()

        try:
            if request.get("hold_auto_exposure"):
                self._hold_auto_exposure()
            else:
                self._apply_exposure(request.get("exposure_ms"))

            self._apply_focus(request.get("focus_distance"))
        except RuntimeError as error:
            reply["error"] = str(error)
            logger.error(f"Camera controls not applied: {error}")
        else:
            reply.update(
                ok=True,
                exposure_ms=self._exposure_ms_readback(),
                exposure_auto=self._exposure_is_auto(),
                focus_distance=self._focus_distance_readback(),
            )

        self.refresh_focus()
        self.refresh_image_settings()
        camera_controls_applied_publisher.publish(reply)

    def _apply_exposure(self, exposure_ms):
        model = self.model

        if exposure_ms is None:
            self.camera.set_auto_exposure()

            # GStreamer backend (Portable Pi): Qt's auto exposure is a no-op
            # there, leaving the camera in manual — switch it over v4l2.
            path = model.v4l2_device_path

            if path is not None:
                if set_v4l2_controls(
                    path, **{V4L2_EXPOSURE_AUTO: V4L2_EXPOSURE_AUTO_ON}
                ):
                    model.v4l2_auto_exposure_path = path
                else:
                    logger.warning(f"v4l2 auto exposure failed for {path}")

            return

        if not self.camera.supports_manual_exposure():
            raise RuntimeError("this camera has no manual exposure")

        # Back to manual on the v4l2 side first, if the fallback above left
        # the camera on auto — its exposure time is ignored otherwise.
        if model.v4l2_auto_exposure_path is not None:
            if not set_v4l2_controls(
                model.v4l2_auto_exposure_path,
                **{V4L2_EXPOSURE_AUTO: V4L2_EXPOSURE_AUTO_MANUAL},
            ):
                logger.warning(
                    f"v4l2 manual exposure restore failed for "
                    f"{model.v4l2_auto_exposure_path}"
                )

            model.v4l2_auto_exposure_path = None

        self.camera.set_manual_exposure(float(exposure_ms))

    @observe("model:v4l2_focus_device_path")
    def _read_v4l2_focus_controls(self, event):
        """Cache the focus device's focus span and whether it has
        continuous auto focus, from one ``v4l2-ctl`` query."""
        model = self.model
        path = event.new
        controls = list_v4l2_controls(path) if path else ""
        auto_focus = parse_v4l2_control_value(controls, V4L2_FOCUS_AUTO)
        control_range = parse_v4l2_control_range(controls, V4L2_FOCUS_ABSOLUTE)
        lens_span = lens_focus_span(model.v4l2_focus_lens_map)

        # A calibrated lens focuses only within its map (on the Pi's
        # imx708 lens, 420-920 of 0-1023), and nearer at higher positions.
        if control_range is not None and lens_span is not None:
            model.v4l2_focus_span = lens_span
        else:
            model.v4l2_focus_span = control_range

        model.v4l2_focus_has_auto = auto_focus is not None

        # A camera left on manual focus (auto off) is the fallback's to
        # drive and to read back from the start.
        if model.v4l2_focus_span is not None and auto_focus == 0:
            model.v4l2_focus_path = path
        else:
            model.v4l2_focus_path = None

    def set_focus(self, focus_distance):
        """Apply the camera panel's focus edit now: ``focus_distance`` from
        0.0 (near) to 1.0 (far), or None for continuous auto focus."""
        self.cancel_autofocus("focus edited")
        self.focus_edits.cancel()

        try:
            self._apply_focus(focus_distance)
        except RuntimeError as error:
            logger.error(f"Focus not applied: {error}")

        self.refresh_focus()

    def request_focus(self, focus_distance):
        """Apply a focus slider drag's ``focus_distance`` (0.0 near to 1.0
        far) live, coalesced into at most one write per
        FOCUS_WRITE_INTERVAL_S that always ends on the latest value."""
        self.cancel_autofocus("focus edited")
        self.focus_edits.submit(focus_distance)

    @observe("model:camera_active")
    def refresh_focus(self, event=None):
        """Mirror the selected camera's focus into ``model.focus``: on every
        source selection, camera on/off (Qt reports focus support only for
        a started camera) and focus change."""
        model = self.model
        focus = model.focus
        qcamera_selected = self._qcamera_selected()
        qt_focus = qcamera_selected and self.camera.supports_manual_focus()
        v4l2_focus = (
            qcamera_selected and not qt_focus and model.v4l2_focus_span is not None
        )

        focus.available = qt_focus or v4l2_focus
        focus.auto_available = qt_focus or (v4l2_focus and model.v4l2_focus_has_auto)
        focus.autofocus_available = focus.available and model.camera_active
        focus.lens_map = model.v4l2_focus_lens_map if v4l2_focus else []
        raw_position = None

        if v4l2_focus:
            # A lens without auto focus holds a position even while no
            # manual focus is applied, so its position is always shown.
            raw_position = get_v4l2_control(
                model.v4l2_focus_device_path, V4L2_FOCUS_ABSOLUTE
            )
            distance = self._v4l2_focus_distance(raw_position)
            focus.auto = model.v4l2_focus_has_auto and model.v4l2_focus_path is None
        elif qt_focus:
            distance = self.camera.focus_distance()
            focus.auto = not self.camera.focus_is_manual()
        else:
            distance = None
            focus.auto = False

        focus.raw_position = raw_position

        if distance is not None:
            focus.distance = distance

    def _qcamera_selected(self):
        """Whether the selected source is a bound QCamera (not a provider
        feed or "<No Camera>")."""
        model = self.model

        return (
            bool(model.selected_camera)
            and not model.provider_selected
            and self.camera.has_camera()
        )

    # ------------------------------------------------------------------ #
    # Image controls (brightness, contrast, ...)                           #
    # ------------------------------------------------------------------ #
    def refresh_image_settings(self):
        """Mirror the selected camera's image controls into
        ``model.image_settings``, on every source selection."""
        settings = []

        if self._qcamera_selected():
            for control in self.camera.image_control_ranges():
                try:
                    value, auto = self.camera.image_control(control.name)
                except RuntimeError as error:
                    logger.error(f"Camera {control.name} not read: {error}")

                    continue

                value = min(max(value, control.low), control.high)

                settings.append(
                    CameraImageSetting(
                        name=control.name,
                        label=IMAGE_CONTROL_LABELS[control.name],
                        low=control.low,
                        high=control.high,
                        default=control.default,
                        value=value,
                        value_text=self.camera.describe_image_control(
                            control.name, value
                        ),
                        has_auto=control.has_auto,
                        auto=auto,
                    )
                )

        self.model.image_settings = settings

    @observe("model:image_settings:items:[value,auto]")
    def _apply_image_setting(self, event):
        """Write a panel edit of an image control to the camera."""
        setting = event.object
        setting.value_text = self.camera.describe_image_control(
            setting.name, setting.value
        )

        try:
            self.camera.set_image_control(setting.name, setting.value, setting.auto)
        except RuntimeError as error:
            logger.error(f"Camera {setting.label} not applied: {error}")

            return

        # Keep the exposure fallback's record of who switched v4l2 auto
        # exposure on, so a later manual-exposure request switches it off.
        if setting.name == EXPOSURE_CONTROL and self.model.v4l2_device_path:
            self.model.v4l2_auto_exposure_path = (
                self.model.v4l2_device_path if setting.auto else None
            )

    @observe("model:reset_image_settings")
    def reset_image_settings(self, event=None):
        """Put every image control back to the camera's default, automatic
        where the control has an automatic mode."""

        for setting in self.model.image_settings:
            setting.trait_set(value=setting.default, auto=setting.has_auto)

    # ------------------------------------------------------------------ #
    # Autofocus (one-shot contrast sweep)                                  #
    # ------------------------------------------------------------------ #
    @observe("model:focus:autofocus_button")
    def start_autofocus(self, event=None):
        """Start a one-shot contrast sweep; live frames then drive it (see
        autofocus_frame)."""
        focus = self.model.focus

        if self.autofocus.running or not focus.autofocus_available:
            return

        self.focus_edits.cancel()
        self._autofocus_started = time.monotonic()
        logger.info("Autofocus sweep started")

        if self._write_focus(self.autofocus.start()):
            self._autofocus_timeout.repeat = 1
            self._autofocus_timeout.start()

    def autofocus_frame(self, grey):
        """Advance the running sweep by one live frame: ``grey`` is its
        centre as a 2-D greyscale array, None when it could not be read."""

        if not self.autofocus.running or grey is None:
            return

        distance = self.autofocus.feed(laplacian_variance(grey))

        if distance is None:
            return

        # A failed write cancels the sweep (logged there).
        written = self._write_focus(distance)

        if self.autofocus.running:
            return

        self._autofocus_timeout.stop()

        if not written:
            return

        autofocus = self.autofocus
        elapsed_s = time.monotonic() - self._autofocus_started

        logger.info(
            f"Autofocus: best focus distance {autofocus.best_distance:.3f} "
            f"(raw {self.model.focus.raw_position}, sharpness "
            f"{autofocus.scores[autofocus.best_distance]:.1f}), "
            f"{len(autofocus.scores)} positions in {elapsed_s:.1f} s"
        )

    def cancel_autofocus(self, reason):
        """Stop a running sweep, leaving the lens where it is."""

        if not self.autofocus.running:
            return

        self.autofocus.cancel()
        self._autofocus_timeout.stop()
        logger.info(f"Autofocus cancelled: {reason}")

    @observe("autofocus:running")
    def _show_autofocus_running(self, event):
        self.model.focus.autofocusing = event.new

    @observe("model:camera_active")
    def _cancel_autofocus_when_stopped(self, event):
        if not event.new:
            self.cancel_autofocus("camera stopped")

    def _autofocus_timed_out(self):
        if self.autofocus.running:
            logger.warning(
                f"Autofocus got too few frames within {AUTOFOCUS_TIMEOUT_S:.0f} s"
            )
            self.cancel_autofocus("timed out")

    def _write_focus(self, focus_distance):
        """Apply a manual ``focus_distance`` and show it without reading
        it back, for slider drags and sweep steps; returns whether it was
        applied."""
        focus = self.model.focus

        try:
            self._apply_focus(focus_distance)
        except RuntimeError as error:
            logger.error(f"Focus not applied: {error}")
            self.cancel_autofocus("focus write failed")
            self.refresh_focus()

            return False

        focus.distance = focus_distance
        focus.auto = False

        if self.model.v4l2_focus_path is not None:
            focus.raw_position = self._v4l2_focus_raw(focus_distance)

        return True

    def _apply_focus(self, focus_distance):
        model = self.model

        if focus_distance is None:
            self.camera.set_auto_focus()

            # Restore continuous auto focus on the v4l2 side too, if the
            # fallback below was last driving this camera's focus.
            if model.v4l2_focus_path is not None and model.v4l2_focus_has_auto:
                if not set_v4l2_controls(model.v4l2_focus_path, **{V4L2_FOCUS_AUTO: 1}):
                    logger.warning(
                        f"v4l2 auto focus restore failed for {model.v4l2_focus_path}"
                    )
            elif model.v4l2_focus_path is not None:
                logger.info(
                    f"{model.v4l2_focus_path} has no auto focus; the lens stays "
                    f"where manual focus left it"
                )

            model.v4l2_focus_path = None

            return

        if self.camera.supports_manual_focus():
            self.camera.set_manual_focus(float(focus_distance))
            model.v4l2_focus_path = None

            return

        # GStreamer backend (Portable Pi): QCamera reports no manual focus
        # support although the camera's v4l2 focus_absolute control works.
        path = model.v4l2_focus_device_path

        if path is None:
            raise RuntimeError("this camera has no manual focus")

        if model.v4l2_focus_span is None:
            raise RuntimeError(
                "this camera has no manual focus (no v4l2 focus_absolute control)"
            )

        raw = self._v4l2_focus_raw(float(focus_distance))
        controls = {V4L2_FOCUS_ABSOLUTE: raw}

        # Auto off first — focus_absolute is inactive while auto is on.
        if model.v4l2_focus_has_auto:
            controls = {V4L2_FOCUS_AUTO: 0, **controls}

        if not set_v4l2_controls(path, **controls):
            raise RuntimeError("v4l2 focus set failed")

        model.v4l2_focus_path = path
        logger.debug(f"Set v4l2 focus_absolute={raw} on {path}")

    def _v4l2_focus_raw(self, focus_distance):
        """``focus_absolute`` position of a focus distance (0.0 to 1.0)."""
        near, far = self.model.v4l2_focus_span

        return round(near + focus_distance * (far - near))

    def _v4l2_focus_distance(self, raw):
        """Focus distance (0.0 to 1.0) of a ``focus_absolute`` position, or
        None for None; a position beyond the span is clamped into it."""

        if raw is None:
            return None

        near, far = self.model.v4l2_focus_span

        if near == far:
            return 0.0

        return min(max((raw - near) / (far - near), 0.0), 1.0)

    def _hold_auto_exposure(self):
        """Switch to manual exposure at the time auto last chose."""
        exposure_ms = self._current_exposure_ms()

        if exposure_ms is None:
            raise RuntimeError("the camera does not report its auto exposure")

        self._apply_exposure(exposure_ms)

    def _exposure_is_auto(self):
        return (
            self.model.v4l2_auto_exposure_path is not None
            or not self.camera.exposure_is_manual()
        )

    def _current_exposure_ms(self):
        """The exposure the camera is using right now (auto's pick
        included), or None when it does not report it."""

        # Under the v4l2 fallback's auto, UVC exposure_time_absolute keeps
        # the last manual value, not auto's pick (checked on the Pi's DH
        # Camera) — nothing reports what auto chose.
        if self.model.v4l2_auto_exposure_path is not None:
            return None

        exposure_ms = self.camera.exposure_time_ms()

        return exposure_ms if exposure_ms > 0 else None

    def _exposure_ms_readback(self):
        if self._exposure_is_auto():
            return self._current_exposure_ms()

        return self.camera.manual_exposure_time_ms()

    def _focus_distance_readback(self):
        model = self.model

        if model.v4l2_focus_path is not None:
            return self._v4l2_focus_distance(
                get_v4l2_control(model.v4l2_focus_path, V4L2_FOCUS_ABSOLUTE)
            )

        if not self.camera.focus_is_manual():
            return None

        return self.camera.focus_distance()
