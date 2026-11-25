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
Publishing is harmless without the notifications plugin: nothing
subscribes."""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from traits.api import Any, Callable, HasTraits, Instance, Int, observe
from traits.observation.api import trait

# Microdrop package imports.
from notifications.consts import (
    SEVERITY_ERROR,
    SEVERITY_SUCCESS,
    notification_publisher,
)

# Local imports.
from ..consts import CAMERA_CAPTURES_CATEGORY_ID, PKG
from ..models.camera import CameraModel
from ..models.capture_session import (
    CaptureSession,
    continues_capture_session,
    format_duration,
    photos_card_text,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The cards' button, opening the folder the capture was saved in.
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
            folder=folder,
            thread_id=session.thread_id,
            pop_up=not quiet,
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

    def video_saved(self, saved_path, quiet=False):
        """Post the recording now at ``saved_path``, with its length;
        ``quiet`` when the user did not ask for it (no toast)."""
        path = Path(saved_path)
        started_at = self._recording_started_at
        stopped_at = self._recording_stopped_at
        detail = path.name

        if started_at is not None and stopped_at is not None:
            detail = f"{path.name} ({format_duration(stopped_at - started_at)})"

        self._post(
            "Video saved",
            detail,
            folder=str(path.parent),
            thread_id=f"{CAMERA_CAPTURES_CATEGORY_ID}.video.{path}",
            pop_up=not quiet,
        )

    # ------------------------------------------------------------------ #
    # Posting                                                              #
    # ------------------------------------------------------------------ #
    def _post(
        self,
        title,
        detail,
        severity=SEVERITY_SUCCESS,
        folder="",
        thread_id="",
        pop_up=True,
    ):
        payload = {
            "title": title,
            "detail": detail,
            "severity": severity,
            "category": "camera",
            "category_id": CAMERA_CAPTURES_CATEGORY_ID,
            "source": PKG,
            "thread_id": thread_id,
            "pop_up": pop_up,
        }

        if folder:
            payload["action"] = {
                "kind": "open_path",
                "label": SHOW_FOLDER_LABEL,
                "path": folder,
            }

        self.post_notification(payload)
