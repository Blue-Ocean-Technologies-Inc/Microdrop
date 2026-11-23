# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Text shown for an entry: its time, its meta line and its tooltip."""

# Standard library imports.
import time
from datetime import datetime

#: How an exact time is written.
EXACT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def format_time(seconds, now=None):
    """When an entry occurred, relative to ``now`` (seconds since the epoch;
    the current time if None): "just now" under a minute, "N min ago" under
    an hour, then the clock time today and the date on other days."""
    now = time.time() if now is None else now
    age = now - seconds

    if age < 60:
        return "just now"

    if age < 3600:
        return f"{int(age // 60)} min ago"

    moment = datetime.fromtimestamp(seconds)

    if moment.date() == datetime.fromtimestamp(now).date():
        return moment.strftime("%H:%M")

    return moment.strftime("%Y-%m-%d")


def format_exact_time(seconds):
    """The full date and time, e.g. "2026-11-23 14:03:22"."""
    return datetime.fromtimestamp(seconds).strftime(EXACT_TIME_FORMAT)


def format_meta(entry):
    """The line under the title, e.g. "log · device_viewer.models"."""
    return " · ".join(part for part in (entry.category, entry.source) if part)


def format_preview(entry):
    """The detail's line shown while collapsed: a traceback's last line
    (the exception), else the first."""
    lines = [line for line in entry.detail.strip().splitlines() if line.strip()]

    if not lines:
        return ""

    return lines[-1] if entry.monospace_detail else lines[0]


def format_tooltip(entry):
    """When the entry occurred, how often, and who posted it."""
    lines = [entry.title, f"Last: {format_exact_time(entry.last_seen)}"]

    if entry.count > 1:
        first_seen = format_exact_time(entry.first_seen)
        lines.append(f"First: {first_seen} ({entry.count} times)")

    if entry.source:
        lines.append(f"From: {entry.source}")

    return "\n".join(lines)
