from typing import Optional, Literal, List, Dict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .consts import DEFAULT_HEATER, OW_RESERVED_KEYS


class _HeaterCommand(BaseModel):
    """Base for per-channel heater commands. ``heater`` defaults to the
    configured fallback channel when a payload omits it."""
    model_config = ConfigDict(extra='forbid')
    heater: str = DEFAULT_HEATER


class SetTemperatureData(_HeaterCommand):
    """PID setpoint -> ``pid_<heater>_<temperature>[_<sensor_group>]``."""
    temperature: float
    sensor_group: Optional[str] = None


class SetPwmData(_HeaterCommand):
    """Open-loop duty -> ``pwm_<heater>_<pwm>``. Duty is a percentage 0-100."""
    pwm: int = Field(ge=0, le=100)


class SetPidModeData(_HeaterCommand):
    """PID run state -> ``pid_<heater>_<mode>``."""
    mode: Literal["enable", "disable", "stop"]


class SetStreamData(BaseModel):
    """Telemetry streaming control. ``group`` is a sensor-group name, ``all`` for
    every sensor, or ``stop`` to halt streaming."""
    model_config = ConfigDict(extra='forbid')
    group: str = "all"


class SetFanData(BaseModel):
    """Fan control -> ``fan_on`` / ``fan_off``."""
    model_config = ConfigDict(extra='forbid')
    on: bool


# --------------------------------------------------------------------------- #
# Configure-sensors-and-heaters edit validation                                #
# --------------------------------------------------------------------------- #

class SensorNaming(BaseModel):
    """A 1-Wire sensor's editable naming: its ROM and the name it's given.
    Empty-named sensors are dropped before validation, so ``name`` is non-empty."""
    model_config = ConfigDict(extra='forbid')
    rom: str
    name: str


class HeaterConfigEdit(BaseModel):
    """Validates a Configure-Sensors-&-Heaters edit before it is written.

    Catches the failure modes the old UI guarded against:
      - a sensor named after a reserved bus key (pin / conv_mode / resolution),
      - duplicate sensor names (which would silently collapse in the config dict),
      - heater assignments referencing names that aren't defined 1-Wire sensors
        or thermistors.
    """
    model_config = ConfigDict(extra='forbid')
    #: Named 1-Wire sensors to persist (empty names already dropped by caller).
    sensors: List[SensorNaming]
    #: heater channel -> list of assigned sensor names.
    assignments: Dict[str, List[str]]
    #: Existing thermistor names (valid assignment targets, not edited here).
    thermistor_names: List[str] = Field(default_factory=list)

    @field_validator("sensors")
    @classmethod
    def _names_valid(cls, sensors):
        names = [s.name for s in sensors]
        reserved = sorted({n for n in names if n in OW_RESERVED_KEYS})
        if reserved:
            raise ValueError(
                f"Sensor name(s) cannot be reserved bus keys: {', '.join(reserved)}")
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"Duplicate sensor name(s): {', '.join(dupes)}")
        return sensors

    @model_validator(mode="after")
    def _references_exist(self):
        defined = {s.name for s in self.sensors} | set(self.thermistor_names)
        unknown = sorted({
            name
            for assigned in self.assignments.values()
            for name in assigned
            if name and name not in defined
        })
        if unknown:
            raise ValueError(
                f"Heater(s) reference undefined sensor(s): {', '.join(unknown)}")
        return self
