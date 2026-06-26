from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field

from .consts import DEFAULT_HEATER


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
