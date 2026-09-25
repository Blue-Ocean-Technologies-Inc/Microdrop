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
and capture bookkeeping (and what it publishes), and exposure/focus requests
with their v4l2 fallbacks for the Portable Pi's GStreamer backend. The Qt
side (QCamera, recorders, frame grabs, dialogs) stays in the view, which
calls in here and acts on the answers.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from traits.api import Callable, HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_application.helpers import get_current_experiment_directory

# Microdrop utils imports.
from microdrop_utils.v4l2_fps_getter import (
    V4L2_EXPOSURE_AUTO,
    V4L2_EXPOSURE_AUTO_MANUAL,
    V4L2_EXPOSURE_AUTO_ON,
    V4L2_FOCUS_ABSOLUTE,
    V4L2_FOCUS_AUTO,
    get_v4l2_control,
    get_v4l2_control_range,
    set_v4l2_controls,
)

# Local imports.
from ..consts import (
    CAPTURES_DIR_NAME,
    MIN_RECORDING_FPS,
    RECORDINGS_DIR_NAME,
    camera_controls_applied_publisher,
    device_viewer_recording_state_publisher,
    media_capture_event_model,
    recording_state_model,
)
from ..interfaces.i_camera_device import ICameraDevice
from ..models.camera import CameraModel
from ..models.media import MediaType
from ..services.media_capture_cache import _cache_media_capture
from ..utils.capture import media_filename

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


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

    @observe("model:camera_active")
    def _remember_camera_state(self, event):
        self.preferences.camera_state = event.new

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
        self, label, remembered_as="", provider=False, v4l2_device_path=None
    ):
        """Record the selected source.

        ``remembered_as`` is saved as the preferred camera — a provider's
        label, a QCamera's Qt description; empty for "<No Camera>", which
        leaves the preference alone.
        """

        if remembered_as:
            self.preferences.selected_camera = remembered_as

        self.model.selected_camera = label
        self.model.provider_selected = provider
        self.model.v4l2_device_path = v4l2_device_path

    def rank_formats(self, formats, allow_strict_mode=True):
        """Indices of the formats to offer, best first, one per resolution.

        ``formats`` holds ``(width, height, pixel_format, frame_rate)`` per
        camera format. Larger resolutions come first; within a resolution
        the preferred pixel format, then the higher frame rate, wins. Under
        the strict-format preference (and ``allow_strict_mode``) only the
        preferred pixel format is offered.
        """
        preferred_format = self.preferences.preferred_video_format.upper()
        strict_mode = self.preferences.strict_video_format and allow_strict_mode

        def sort_key(index):
            width, height, pixel_format, frame_rate = formats[index]

            return (
                width,
                height,
                preferred_format in pixel_format.upper(),
                frame_rate,
            )

        ranked = []
        seen_resolutions = set()

        for index in sorted(range(len(formats)), key=sort_key, reverse=True):
            width, height, pixel_format, _ = formats[index]

            if strict_mode and preferred_format not in pixel_format.upper():
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

    def _apply_focus(self, focus_distance):
        model = self.model

        if focus_distance is None:
            self.camera.set_auto_focus()

            # Restore continuous auto focus on the v4l2 side too, if the
            # fallback below was last driving this camera's focus.
            if model.v4l2_focus_path is not None:
                if not set_v4l2_controls(model.v4l2_focus_path, **{V4L2_FOCUS_AUTO: 1}):
                    logger.warning(
                        f"v4l2 auto focus restore failed for {model.v4l2_focus_path}"
                    )

                model.v4l2_focus_path = None

            return

        if self.camera.supports_manual_focus():
            self.camera.set_manual_focus(float(focus_distance))
            model.v4l2_focus_path = None

            return

        # GStreamer backend (Portable Pi): QCamera reports no manual focus
        # support although the camera's v4l2 focus_absolute control works.
        path = model.v4l2_device_path

        if path is None:
            raise RuntimeError("this camera has no manual focus")

        if path != model.v4l2_focus_path or model.v4l2_focus_range is None:
            model.v4l2_focus_range = get_v4l2_control_range(path, V4L2_FOCUS_ABSOLUTE)

        if model.v4l2_focus_range is None:
            raise RuntimeError(
                "this camera has no manual focus (no v4l2 focus_absolute control)"
            )

        lo, hi = model.v4l2_focus_range
        raw = round(lo + float(focus_distance) * (hi - lo))

        # Auto off first — focus_absolute is inactive while auto is on.
        if not set_v4l2_controls(
            path, **{V4L2_FOCUS_AUTO: 0, V4L2_FOCUS_ABSOLUTE: raw}
        ):
            raise RuntimeError("v4l2 focus set failed")

        model.v4l2_focus_path = path
        logger.info(f"Set v4l2 focus_absolute={raw} on {path}")

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
            lo, hi = model.v4l2_focus_range
            raw = get_v4l2_control(model.v4l2_focus_path, V4L2_FOCUS_ABSOLUTE)

            return (raw - lo) / (hi - lo) if raw is not None else None

        if not self.camera.focus_is_manual():
            return None

        return self.camera.focus_distance()
