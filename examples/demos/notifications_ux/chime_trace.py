# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""An opt-in trace of everything the chime does, for a silence to be
explained after the fact: set MICRODROP_CHIME_LOG to a file path and each
event appends one line, ``HH:MM:SS.mmm event key=value ...``. Unset, a
trace call returns at once.
"""

# Standard library imports.
import os
import time

#: The environment variable naming the trace file.
CHIME_LOG_ENV = "MICRODROP_CHIME_LOG"

#: The open trace file; None until the first event, False when off.
_file = None


def enabled():
    """Whether events are traced this session."""
    return bool(os.environ.get(CHIME_LOG_ENV))


def trace(event, **fields):
    """Append ``event`` and its fields to the trace file, if one is set."""
    global _file

    if _file is False:
        return

    if _file is None:
        path = os.environ.get(CHIME_LOG_ENV)

        if not path:
            _file = False

            return

        _file = open(path, "a", encoding="utf-8", buffering=1)

    now = time.time()
    stamp = (
        time.strftime("%H:%M:%S", time.localtime(now))
        + f".{int(now * 1000) % 1000:03d}"
    )
    details = " ".join(f"{key}={value!r}" for key, value in fields.items())

    _file.write(f"{stamp} {event} {details}\n")
