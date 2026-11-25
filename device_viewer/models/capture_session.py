# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Which photos one notification card counts, and what the camera's capture
cards say. Pure functions of the captures; Qt-free."""

# Enthought library imports.
from traits.api import Any, Float, HasTraits, Int, Str

# Local imports.
from ..consts import CAPTURE_SESSION_WINDOW_S


class CaptureSession(HasTraits):
    """The photos one card counts, updated in place by each new one."""

    #: The folder they are saved in.
    folder = Str()

    #: The protocol run they were saved during; None outside a run.
    run = Any()

    #: How many were saved.
    count = Int()

    #: ``time.monotonic()`` of the latest.
    last_saved_at = Float()

    #: The card's thread: posts naming it update the one card.
    thread_id = Str()


def continues_capture_session(
    session, folder, run, now, window_s=CAPTURE_SESSION_WINDOW_S
):
    """Whether a photo saved into ``folder`` at ``now`` joins ``session``.

    A session is one folder and one protocol run: every photo of a run (and
    a capture button press during it) joins its card. Outside a run, a photo
    joins while it lands in the same folder within ``window_s`` seconds of
    the previous one; a different folder, a run starting, or a longer pause
    starts a new card.

    Parameters
    ----------
    session
        The current CaptureSession; None before the first photo.
    run
        The number of the protocol run under way; None outside a run.
    now
        ``time.monotonic()`` of the photo.
    """

    if session is None:
        return False

    if (session.folder, session.run) != (folder, run):
        return False

    return run is not None or now - session.last_saved_at <= window_s


def photos_card_text(count, file_name):
    """The ``(title, detail)`` of a card counting ``count`` photos, the
    latest saved as ``file_name``."""

    if count == 1:
        return "Photo captured", file_name

    return f"{count} photos captured", f"Latest: {file_name}"


def format_duration(seconds):
    """``seconds`` as ``m:ss``, e.g. "1:05"; ``h:mm:ss`` from an hour."""
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"
