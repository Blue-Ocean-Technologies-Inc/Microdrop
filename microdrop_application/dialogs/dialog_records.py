# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Record the errors and warnings shown as dialogs in the notifications
drawer: listed in Activity and counted on the bell, with no toast and no
sound, since the dialog itself is the interruption.

``pyface_wrapper.error`` and ``warning`` record by default; ``information``
and ``success`` only when asked; ``confirm``, ``choose`` and ``disclaimer``
never (a question is not an event). Each of the four takes three keywords:

- ``record``: False keeps an error or warning out of the drawer (e.g.
  feedback on a form being filled in); True records an information or
  success dialog.
- ``source``: who raised it, shown on the entry; DIALOG_SOURCE if not given.
- ``help_target``: a HelpAction target (``notifications.consts.help_target``)
  giving the entry its "How do Iâ€¦?" link.

The entry is posted before the dialog opens, so it is listed even while the
modal dialog holds the event loop. Without the notifications plugin the
post has no listener and nothing is listed.
"""

# Standard library imports.
import html
import re
import time

# Microdrop package imports.
from notifications.consts import (
    CATEGORY_ID_DIALOG_ALERTS,
    notification_publisher,
)

# Local imports.
from .consts import (
    DIALOG_DETAIL_MAX_CHARS,
    DIALOG_REPEAT_WINDOW_S,
    DIALOG_SOURCE,
    GENERIC_DIALOG_TITLES,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: A tag, as rich dialog text has them.
_TAG_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")

#: Tags ending a line.
_LINE_BREAK_PATTERN = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?\s*>", re.I)

#: Per dialog ``(severity, title, text)``: its latest occurrence and when it
#: was last shown. Dialogs are shown at a human pace, so this stays small.
_latest_occurrences = {}


def plain_text(text):
    """``text`` without its markup, if it has any: line-ending tags become
    line breaks, the rest go, entities are decoded. Plain text is kept as
    is, indentation included (a traceback)."""
    text = (text or "").strip()

    if not _TAG_PATTERN.search(text):
        return text

    text = _TAG_PATTERN.sub("", _LINE_BREAK_PATTERN.sub("\n", text))
    lines = [line.strip() for line in html.unescape(text).splitlines()]

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def dialog_occurrence(previous, now, window_s=DIALOG_REPEAT_WINDOW_S):
    """The occurrence a dialog shown at ``now`` belongs to: its ``previous``
    showing's ``(occurrence, shown_at)`` within ``window_s`` seconds of it, a
    burst from one cause; else a new one, named by ``now``."""

    if previous is not None and now - previous[1] <= window_s:
        return previous[0]

    return f"{now:.3f}"


def dialog_notification(
    severity,
    title,
    text,
    detail="",
    source=DIALOG_SOURCE,
    help_target="",
    occurrence="",
):
    """The NotificationMessage payload recording a dialog: quiet (no toast,
    no sound) whatever its category's settings say, as the dialog already
    interrupted the user."""
    title = plain_text(title)
    text = plain_text(text)

    # "Error" says nothing the red glyph does not: the first line does.
    if not title or title in GENERIC_DIALOG_TITLES:
        first_line, _newline, rest = text.partition("\n")
        title, text = first_line or title or severity.title(), rest.strip()

    detail = "\n\n".join(part for part in (text, plain_text(detail)) if part)

    if len(detail) > DIALOG_DETAIL_MAX_CHARS:
        detail = f"{detail[: DIALOG_DETAIL_MAX_CHARS - 1]}â€¦"

    payload = {
        "title": title,
        "detail": detail,
        "severity": severity,
        "source": source,
        "category_id": CATEGORY_ID_DIALOG_ALERTS,
        "occurrence": occurrence,
        "pop_up": False,
    }

    if help_target:
        payload["secondary_action"] = {"kind": "help", "target": help_target}

    return payload


def record_dialog(
    severity, title, text, detail="", source=DIALOG_SOURCE, help_target=""
):
    """Post the quiet entry for a dialog about to show. A repeat within
    DIALOG_REPEAT_WINDOW_S joins its entry; a later one is a new entry."""
    now = time.time()
    key = (severity, title, text)
    occurrence = dialog_occurrence(_latest_occurrences.get(key), now)
    _latest_occurrences[key] = (occurrence, now)

    payload = dialog_notification(
        severity, title, text, detail or "", source, help_target, occurrence
    )

    try:
        notification_publisher.publish(payload)

    # The dialog still shows. Logged, the failure reaches the drawer through
    # the log forwarder when the notifications plugin runs in this process.
    except Exception as error:
        logger.warning(f"Could not record the dialog {title!r}: {error}")


def record_from_kwargs(
    kwargs, severity, title, message, informative=None, detail=None, record=True
):
    """Take the recording keywords out of a wrapper dialog's ``kwargs`` and
    record the dialog when asked; ``record`` is the wrapper's default."""
    record = kwargs.pop("record", record)
    source = kwargs.pop("source", DIALOG_SOURCE)
    help_target = kwargs.pop("help_target", "")

    if record:
        record_dialog(
            severity, title, informative or message, detail, source, help_target
        )
