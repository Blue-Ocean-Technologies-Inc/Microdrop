# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater loop bounds, protocol temperature steps, and the heater
message contracts."""

# Third-party imports.
from pydantic import BaseModel, Field, model_validator

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Local imports.
from .topics import TEMP_SET_PID, TEMPERATURE_REACHED

#: The board has two heater loops: tempctrl channels 0 and 1, the vendor
#: UI's "Heater 1 · ch 0" and "Heater 2 · ch 1".
TEMP_CHANNEL_MAX = 1
#: The MCU refuses TEMP_SET_TARGET at or above the board's heater failsafe
#: max temperature (heat_fs max_temp_c) minus this margin.
TEMP_TARGET_MAX_MARGIN_C = 5.0
#: Target bounds for the UI: the vendor UI's floor, and just under the
#: refusal at the firmware's default max_temp_c (120 - 5 = 115 °C). The
#: backend re-checks every target against the max_temp_c the board serves.
TEMP_TARGET_C_BOUNDS = (-50.0, 114.9)
#: MCU 1.0.1.31 refuses TEMP_SET_PARAMS with a gain above 100, and with
#: Kp = Ki = 0 (the loop would never drive the heater). The period is a
#: uint16 on the wire (DroSIG 1.0.1.33, dropbot-portable 1.8.0), so the
#: vendor UI's 65535 ms is the ceiling.
TEMP_PID_GAIN_BOUNDS = (0.0, 100.0)
TEMP_PID_PERIOD_MS_BOUNDS = (1, 65_535)
#: The heater failsafe alarms (always on since MCU 1.0.1.30): 09001 a
#: sensor above max_temp_c, 09002 no temperature rise at full power
#: (heater disconnected?), 09004 no host bytes for host_silence_s, 09005 a
#: stale control sensor. Each switches its loop off until it is restarted,
#: so a protocol step waiting on that loop fails.
HEATER_FAILSAFE_ALARM_CODES = ("09001", "09002", "09004", "09005")

#: Protocol-step contracts (portable_dropbot_protocol_controls drives
#: these). The heater channel a protocol's temperature column targets:
#: the column carries no channel cell, so it always drives this one.
DEFAULT_TEMP_CHANNEL = 0
#: How the backend watches for a protocol setpoint being reached:
#: poll the channel reading this often, and give up (no reached ack,
#: the step times out) after this long.
TEMP_REACHED_POLL_INTERVAL_S = 1.0
TEMP_REACHED_TIMEOUT_S = 600.0

# --------------------------------------------------------------------- #
# Heater message contracts (topic + schema, one unit)                    #
# --------------------------------------------------------------------- #


class TempSetTargetRequest(BaseModel):
    """A heater loop's target. The backend also refuses a target at or
    above the board's max_temp_c minus TEMP_TARGET_MAX_MARGIN_C."""

    channel: int = Field(ge=0, le=TEMP_CHANNEL_MAX)
    target_c: float = Field(ge=TEMP_TARGET_C_BOUNDS[0])


class ProtocolSetTemperatureRequest(TempSetTargetRequest):
    """A protocol step's setpoint, acked on TEMPERATURE_REACHED once the
    reading is within `tolerance_c` of the target."""

    tolerance_c: float = Field(ge=0)


class TempSetPidRequest(BaseModel):
    """A heater loop's PID tuning, inside what MCU 1.0.1.31 accepts. The
    gains travel in hundredths, rounded as the driver's proxy does, so a
    gain up to 0.005 is 0 on the wire."""

    channel: int = Field(ge=0, le=TEMP_CHANNEL_MAX)
    kp: float = Field(ge=TEMP_PID_GAIN_BOUNDS[0], le=TEMP_PID_GAIN_BOUNDS[1])
    ki: float = Field(ge=TEMP_PID_GAIN_BOUNDS[0], le=TEMP_PID_GAIN_BOUNDS[1])
    kd: float = Field(ge=TEMP_PID_GAIN_BOUNDS[0], le=TEMP_PID_GAIN_BOUNDS[1])
    period_ms: int = Field(
        ge=TEMP_PID_PERIOD_MS_BOUNDS[0], le=TEMP_PID_PERIOD_MS_BOUNDS[1]
    )

    @model_validator(mode="after")
    def _loop_drives_the_heater(self):
        if round(self.kp / 0.01) == 0 and round(self.ki / 0.01) == 0:
            raise ValueError(
                "Kp and Ki cannot both be 0: the firmware refuses a loop "
                "that would never drive the heater"
            )

        return self


class TemperatureReached(BaseModel):
    """A protocol temperature step's outcome: the reading that settled
    within tolerance, or `error` when the step failed."""

    channel: int
    current_c: float | None = None
    error: str = ""


temp_set_pid_publisher = ValidatedTopicPublisher(
    topic=TEMP_SET_PID, validator_class=TempSetPidRequest
)
temperature_reached_publisher = ValidatedTopicPublisher(
    topic=TEMPERATURE_REACHED, validator_class=TemperatureReached
)
