# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What the MCU's heater control refuses and when it gives up, as the
driver documents it (dropbot_portable.proxy TEMP_SET_TARGET /
TEMP_START_STOP, param_layout heat_fs): the target ceiling below the
board's failsafe max temperature, and the failsafe alarms that switch a
running loop off. Pure helpers, unit-testable without hardware."""

# Standard library imports.
import re

# Local imports.
from .consts import HEATER_FAILSAFE_ALARM_CODES, TEMP_TARGET_MAX_MARGIN_C

#: The alarm code a legacy display string starts with ("[09002] ...").
_ALARM_TEXT_CODE = re.compile(r"^\[(\d{5})\]")
#: The heater loop a failsafe alarm's board description names ("htr0").
_ALARM_HEATER_CHANNEL = re.compile(r"\bhtr(\d)\b")


def heater_target_refusal(target_c, max_temp_c):
    """Why the MCU would refuse this target on a board whose failsafe max
    temperature is ``max_temp_c``, or "" when it accepts it."""
    limit_c = max_temp_c - TEMP_TARGET_MAX_MARGIN_C

    if target_c < limit_c:
        return ""

    return (
        f"target {target_c:g} °C refused: the board accepts targets below "
        f"{limit_c:g} °C (its heater max temperature {max_temp_c:g} °C minus "
        f"{TEMP_TARGET_MAX_MARGIN_C:g} °C)"
    )


def _alarm_entries(alarm_raised):
    """An AlarmRaised's alarms as (code, active, text). Payloads without the
    decoded reports carry only the display strings: the code is read from
    their "[code]" prefix and every entry counts as a raise."""
    if alarm_raised.reports:
        return [
            (report.code, report.active, f"{report.text} {report.detail}")
            for report in alarm_raised.reports
        ]

    entries = []

    for text in alarm_raised.alarms:
        match = _ALARM_TEXT_CODE.match(text)
        entries.append((match.group(1) if match else None, None, text))

    return entries


def heater_failsafe_alarms(alarm_raised):
    """The heater failsafe alarms an AlarmRaised raises (clears skipped), as
    (code, channel, text); channel is None when the alarm does not name its
    loop (09004, host silence, stops every running loop)."""
    alarms = []

    for code, active, text in _alarm_entries(alarm_raised):
        if code not in HEATER_FAILSAFE_ALARM_CODES or active == 0:
            continue

        channel = _ALARM_HEATER_CHANNEL.search(text)
        alarms.append((code, int(channel.group(1)) if channel else None, text))

    return alarms
