# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Clear latched board alarms through the driver (dropbot-portable 1.8.0):
read the active ones (GET_ALARMS), clear each (CLEAR_ALARM), read again.

The re-read is the verdict, not the clear's reply: the signal board answers
a refused clear of a ``failure``-level alarm with a reply all the same, so
an alarm whose condition persists shows up as still active."""


def read_active_alarms(session, board):
    """The alarms latched on ``board``, code -> title; None when they could
    not be read (no reply, or the board is not logged in)."""
    alarms = session.uart.get_alarms(board)

    # False as well as None: the vendor self-test treats both as no reply.
    if alarms is None or alarms is False:
        return None

    return {alarm["code"]: alarm.get("title") or alarm["text"] for alarm in alarms}


def clear_board_alarms(session, board, codes=()):
    """Clear ``codes`` on ``board`` (every active alarm when empty) and say
    how it went, in the BoardAlarmsCleared shape."""
    active = read_active_alarms(session, board)

    if active is None and not codes:
        return {"board": board, "error": "active alarms could not be read"}

    targets = list(codes) or list(active)
    refused = [code for code in targets if not session.clear_alarm(board, code)]
    still_active = read_active_alarms(session, board)
    error = ""

    if still_active is None:
        error = "active alarms could not be read after the clear"
        still_active = {}

    failed = [code for code in targets if code in refused or code in still_active]

    return {
        "board": board,
        "cleared": [code for code in targets if code not in failed],
        "failed": failed,
        "still_active": still_active,
        "error": error,
    }


def summarize_alarms_cleared(results):
    """One line per board for the log: what cleared, what failed, what is
    still active."""
    lines = []

    for result in results:
        if result.error and not (result.cleared or result.failed):
            lines.append(f"{result.board}: {result.error}")
            continue

        parts = [f"cleared {', '.join(result.cleared) or 'none'}"]

        if result.failed:
            parts.append(f"failed {', '.join(result.failed)}")

        if result.still_active:
            parts.append(f"still active {', '.join(sorted(result.still_active))}")

        if result.error:
            parts.append(result.error)

        lines.append(f"{result.board}: {'; '.join(parts)}")

    return " | ".join(lines)
