# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""HV halt and enable status bits, and the alarm, alarm-clear and
firmware-version message contracts."""

# Standard library imports.
from typing import Annotated, Literal

# Third-party imports.
from pydantic import BaseModel, Field

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Local imports.
from .topics import (
    ALARM_RAISED,
    ALARMS_CLEARED,
    CLEAR_ALARMS,
    FIRMWARE_VERSIONS_UPDATED,
)

#: STATUS hv_state bit3: the firmware latched a halt (an HV deviation,
#: chip-load saturation or short-circuit halt; vendor data_report.HV_HALTED).
HV_STATE_HALTED_BIT = 0x08
#: HV_ENABLE reply status bytes that answer a request (on / off); 2-5 are
#: refusals, see the vendor's self_test.HV_ENABLE_STATUS_TEXT.
HV_ENABLE_STATUS_ON = 0
HV_ENABLE_STATUS_OFF = 1
#: The boards that latch alarms, as the driver's clear_alarm names them.
ALARM_BOARDS = ("motor", "signal")

# --------------------------------------------------------------------- #
# Board health message contracts (topic + schema, one unit)              #
# --------------------------------------------------------------------- #


class AlarmReportEntry(BaseModel):
    """One decoded REPORT_ALARM push (the driver's AlarmReport fields).
    `active` 0 is the board clearing the alarm; None is a frame without the
    header bytes, read as a raise."""

    text: str
    code: str | None = None
    title: str = ""
    detail: str = ""
    active: int | None = None
    level: int | None = None


class AlarmRaised(BaseModel):
    """A REPORT_ALARM frame. `alarms` keeps the legacy display strings."""

    command: str
    alarms: list[str] = []
    reports: list[AlarmReportEntry] = []


alarm_raised_publisher = ValidatedTopicPublisher(
    topic=ALARM_RAISED, validator_class=AlarmRaised
)


class ClearAlarmsRequest(BaseModel):
    """Clear latched alarms on `boards`: the listed `codes` (5 digits, e.g.
    04012), or every alarm active on each board when `codes` is empty."""

    boards: list[Literal[ALARM_BOARDS]] = list(ALARM_BOARDS)
    codes: list[Annotated[str, Field(pattern=r"^\d{5}$")]] = []


clear_alarms_publisher = ValidatedTopicPublisher(
    topic=CLEAR_ALARMS, validator_class=ClearAlarmsRequest
)


class BoardAlarmsCleared(BaseModel):
    """One board's clear: `cleared` codes are gone on the re-read; `failed`
    codes were refused or are still active (their condition persists);
    `still_active` is the re-read, code -> title. `error` says the alarms
    could not be read, or the board did not answer at all."""

    board: str
    cleared: list[str] = []
    failed: list[str] = []
    still_active: dict[str, str] = {}
    error: str = ""


class AlarmsCleared(BaseModel):
    """The outcome of a CLEAR_ALARMS request, one entry per board asked."""

    results: list[BoardAlarmsCleared] = []


alarms_cleared_publisher = ValidatedTopicPublisher(
    topic=ALARMS_CLEARED, validator_class=AlarmsCleared
)


class FirmwareVersionsUpdated(BaseModel):
    """The running firmware tags ("" when unknown), and one line per board
    below the driver bindings' minimum."""

    mcu: str = ""
    motor: str = ""
    outdated: list[str] = []


firmware_versions_publisher = ValidatedTopicPublisher(
    topic=FIRMWARE_VERSIONS_UPDATED, validator_class=FirmwareVersionsUpdated
)
