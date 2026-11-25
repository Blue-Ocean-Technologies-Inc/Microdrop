# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Posts the camera panel's photos and videos to the notifications drawer
(Camera > Captures), where the status bar used to show them for a few
seconds: one card per capture session (see continues_capture_session),
updated in place, and one per video. Captures a protocol or another plugin
asked for are posted quietly (no toast, no sound); the user's own pop up.
A card's Show button shows the capture in its viewer (the Image Viewer, the
Recording Viewer); while that viewer's plugin is not running it is a Show
folder button instead. A card's thumbnail is the photo (the latest of a
session) or the recording's poster, and the file name in its text links to
the folder. Publishing is harmless without the notifications plugin:
nothing subscribes."""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from traits.api import Any, Callable, HasTraits, Instance, Int, observe
from traits.observation.api import trait

# Microdrop package imports.
from image_viewer.consts import LISTENER_NAME as IMAGE_VIEWER_LISTENER_NAME
from image_viewer.consts import SHOW_IMAGE, ShowImageRequest
from notifications.consts import (
    SEVERITY_ERROR,
    SEVERITY_SUCCESS,
    notification_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import is_dramatiq_listener_registered

# Local imports.
from ..consts import CAMERA_CAPTURES_CATEGORY_ID, PKG
from ..models.camera import CameraModel
from ..models.capture_session import (
    CaptureSession,
    continues_capture_session,
    format_duration,
    photos_card_text,
)
from ..recording_viewer_consts import (
    RECORDING_VIEWER_LISTENER_NAME,
    SHOW_RECORDING,
    ShowRecordingRequest,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The cards' button, showing the capture in its viewer.
SHOW_LABEL = "Show"

#: The cards' button while the capture's viewer is not running, opening the
#: folder the capture was saved in.
SHOW_FOLDER_LABEL = "Show folder"


class CaptureNotificationsController(HasTraits):
    """Posts photos captured, videos saved and failed captures."""

    #: The camera panel's state: when a recording starts and stops.
    camera_model = Instance(CameraModel, ())

    #: The device viewer's model: whether a protocol is running.
    main_model = Any()

    #: ``post_notification(payload)``: posts a NotificationMessage payload;
    #: publishes it on NOTIFICATION_POST by default (no listener, no-op).
    post_notification = Callable()

    #: ``viewer_running(listener_name)``: whether the viewer listening as
    #: ``listener_name`` is running, so its card's Show button is heard.
    viewer_running = Callable(is_dramatiq_listener_registered)

    #: The photos the latest card counts; None before the first.
    _session = Instance(CaptureSession)

    #: Sessions started, numbering their cards' threads.
    _sessions_started = Int()

    #: Protocol runs started, numbering their sessions.
    _runs_started = Int()

    #: ``time.monotonic()`` of the recording's start and stop; None unknown.
    _recording_started_at = Any()
    _recording_stopped_at = Any()

    def _post_notification_default(self):
        return notification_publisher.publish

    # ------------------------------------------------------------------ #
    # Photos                                                               #
    # ------------------------------------------------------------------ #
    def photo_saved(self, saved_path, quiet=False):
        """Count the photo now at ``saved_path`` on its session's card;
        ``quiet`` when the user did not ask for it (no toast)."""
        path = Path(saved_path)
        folder = str(path.parent)
        run = self._run()
        now = time.monotonic()

        if not continues_capture_session(self._session, folder, run, now):
            self._sessions_started += 1
            self._session = CaptureSession(
                folder=folder,
                run=run,
                thread_id=f"{CAMERA_CAPTURES_CATEGORY_ID}.photos."
                f"{self._sessions_started}",
            )

        session = self._session
        session.count += 1
        session.last_saved_at = now
        title, detail = photos_card_text(session.count, path.name)

        self._post(
            title,
            detail,
            action=self._show_action(
                path, IMAGE_VIEWER_LISTENER_NAME, SHOW_IMAGE, ShowImageRequest
            ),
            thread_id=session.thread_id,
            pop_up=not quiet,
            thumbnail=str(path),
            linked_file=path,
        )

    def photo_failed(self, reason):
        """Post a photo that could not be captured, and why."""
        # Info, not error: the log forwarder would post an error record as
        # a second card for the same failure.
        logger.info(f"Photo not captured: {reason}")
        self._post("Photo not captured", reason, severity=SEVERITY_ERROR)

    def _run(self):
        """The number of the protocol run under way; None outside a run."""
        running = getattr(self.main_model, "protocol_running", False)

        return self._runs_started if running else None

    @observe(trait("main_model", notify=False).trait("protocol_running", optional=True))
    def _count_protocol_runs(self, event):

        if event.new:
            self._runs_started += 1

    # ------------------------------------------------------------------ #
    # Videos                                                               #
    # ------------------------------------------------------------------ #
    @observe("camera_model:recording:active")
    def _time_recording(self, event):
        now = time.monotonic()

        if event.new:
            self._recording_started_at = now
            self._recording_stopped_at = None
        else:
            self._recording_stopped_at = now

    def video_saved(self, saved_path, quiet=False, poster_path=None):
        """Post the recording now at ``saved_path``, with its length;
        ``quiet`` when the user did not ask for it (no toast). Its card's
        thumbnail is ``poster_path`` (a still saved beside it), else the
        recording itself, which the card shows as a film glyph."""
        path = Path(saved_path)
        started_at = self._recording_started_at
        stopped_at = self._recording_stopped_at
        detail = path.name

        if started_at is not None and stopped_at is not None:
            detail = f"{path.name} ({format_duration(stopped_at - started_at)})"

        self._post(
            "Video saved",
            detail,
            action=self._show_action(
                path,
                RECORDING_VIEWER_LISTENER_NAME,
                SHOW_RECORDING,
                ShowRecordingRequest,
            ),
            thread_id=f"{CAMERA_CAPTURES_CATEGORY_ID}.video.{path}",
            pop_up=not quiet,
            thumbnail=str(poster_path or path),
            linked_file=path,
        )

    # ------------------------------------------------------------------ #
    # Posting                                                              #
    # ------------------------------------------------------------------ #
    def _show_action(self, path, listener_name, topic, request_class):
        """The card's button for the capture at ``path``: Show, publishing
        ``request_class`` on ``topic`` for the viewer listening as
        ``listener_name``; Show folder while that viewer is not running, as
        nothing would hear Show."""

        if self.viewer_running(listener_name):
            return {
                "kind": "publish",
                "label": SHOW_LABEL,
                "topic": topic,
                "message": request_class(path=str(path)).model_dump_json(),
            }

        return {
            "kind": "open_path",
            "label": SHOW_FOLDER_LABEL,
            "path": str(path.parent),
        }

    def _post(
        self,
        title,
        detail,
        severity=SEVERITY_SUCCESS,
        action=None,
        thread_id="",
        pop_up=True,
        thumbnail="",
        linked_file=None,
    ):
        """Post a card; ``linked_file``'s name in the detail links to its
        folder (the file's path is the link's tooltip)."""
        links = []

        if linked_file is not None:
            links.append({"text": linked_file.name, "path": str(linked_file)})

        payload = {
            "title": title,
            "detail": detail,
            "severity": severity,
            "category": "camera",
            "category_id": CAMERA_CAPTURES_CATEGORY_ID,
            "source": PKG,
            "thread_id": thread_id,
            "pop_up": pop_up,
            "action": action,
            "thumbnail": thumbnail,
            "links": links,
        }

        self.post_notification(payload)
