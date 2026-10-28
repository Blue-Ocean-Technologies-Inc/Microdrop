# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free battery state, fed from rpi-battery-monitor status snapshots."""

# Standard library imports.
from numbers import Real

# Enthought library imports.
from traits.api import Bool, Float, HasTraits, Int, Property, Str, Union

# Local imports.
from ..consts import (
    CHARGING_GLYPHS,
    CRITICAL_PERCENT,
    DISCHARGING_GLYPHS,
    LEVEL_ABSENT,
    LEVEL_ALERT,
    LEVEL_CRITICAL,
    LEVEL_LOW,
    LEVEL_NORMAL,
    LEVEL_UNAVAILABLE,
    LOW_PERCENT,
    STALE_AFTER_S,
    UNKNOWN_GLYPH,
    UNKNOWN_PERCENT_TEXT,
    UNKNOWN_SENTINEL,
)


def _number_or_none(value):
    """Return ``value`` as a float, or None when it is not a real number."""
    if isinstance(value, Real) and not isinstance(value, bool):
        return float(value)

    return None


def _duration_or_none(value):
    """Return a time / charge value, or None for null and the -1 sentinel."""
    number = _number_or_none(value)

    if number == UNKNOWN_SENTINEL:
        return None

    return number


def _format_duration(seconds):
    """Return ``seconds`` as e.g. ``"1 h 05 min"`` or ``"42 min"``."""
    hours, minutes = divmod(round(seconds / 60), 60)

    if hours:
        return f"{hours} h {minutes:02d} min"

    return f"{minutes} min"


class BatteryStatus(HasTraits):
    """The battery as last reported by the daemon.

    No clock and no IO: the caller hands in each parsed snapshot together
    with the current time, or reports the daemon unreachable.
    """

    #: State of charge in percent (0-100); None while unknown.
    percentage = Union(None, Float)

    #: Pack voltage (V); None while unknown.
    voltage = Union(None, Float)

    #: Pack current (A), positive while discharging; None while unknown.
    current = Union(None, Float)

    #: Estimated seconds until empty (snapshot key time_to_empty_s); None
    #: while unknown or charging.
    time_to_empty = Union(None, Float)

    #: Estimated seconds until full (snapshot key time_to_full_s); None
    #: while unknown or discharging.
    time_to_full = Union(None, Float)

    #: Whether the pack is charging.
    charging = Bool(False)

    #: Whether the INA226 low-voltage ALERT is raised.
    alert = Bool(False)

    #: Whether the sensor reads the charger rail with no pack connected; the
    #: percentage is meaningless then.
    battery_absent = Bool(False)

    #: Whether the last snapshot is fresh, i.e. the daemon is running.
    alive = Bool(False)

    #: Unix time (s) the daemon wrote the last snapshot; None if never.
    timestamp = Union(None, Float)

    #: Precedence level that sets the icon colour; rules in _get_level.
    level = Property(Str, observe=["alive", "battery_absent", "alert", "percentage"])

    #: Whether the percentage means anything: daemon alive, pack present,
    #: state of charge known.
    percentage_known = Property(Bool, observe=["alive", "battery_absent", "percentage"])

    #: Index into the glyph lists, 0 (empty) to 7 (full); None while the
    #: percentage is not known.
    fill_bucket = Property(Union(None, Int), observe=["percentage_known", "percentage"])

    #: Material Symbols ligature: fill tracks the percentage, charging
    #: variant while charging.
    glyph = Property(Str, observe=["fill_bucket", "charging"])

    #: Rounded percentage shown beside the glyph, e.g. "34 %".
    percent_text = Property(Str, observe=["percentage_known", "percentage"])

    #: Plain-text details for the icon's tooltip.
    tooltip = Property(
        Str,
        observe=[
            "level",
            "percentage",
            "voltage",
            "current",
            "charging",
            "time_to_empty",
            "time_to_full",
        ],
    )

    def apply_snapshot(self, snapshot, now):
        """Take in a parsed status-file snapshot read at unix time ``now``.

        Missing keys and values of the wrong type read as unknown.
        """
        timestamp = _number_or_none(snapshot.get("timestamp"))

        self.trait_set(
            percentage=_number_or_none(snapshot.get("soc")),
            voltage=_number_or_none(snapshot.get("voltage")),
            current=_number_or_none(snapshot.get("current")),
            time_to_empty=_duration_or_none(snapshot.get("time_to_empty_s")),
            time_to_full=_duration_or_none(snapshot.get("time_to_full_s")),
            charging=snapshot.get("charging") is True,
            alert=snapshot.get("alert") is True,
            battery_absent=snapshot.get("battery_absent") is True,
            timestamp=timestamp,
            alive=timestamp is not None and now - timestamp < STALE_AFTER_S,
        )

    def mark_unavailable(self):
        """Record that no snapshot could be read."""
        self.alive = False

    def _get_level(self):
        if not self.alive:
            return LEVEL_UNAVAILABLE

        if self.battery_absent:
            return LEVEL_ABSENT

        if self.alert:
            return LEVEL_ALERT

        if self.percentage is not None and self.percentage < CRITICAL_PERCENT:
            return LEVEL_CRITICAL

        if self.percentage is not None and self.percentage < LOW_PERCENT:
            return LEVEL_LOW

        return LEVEL_NORMAL

    def _get_percentage_known(self):
        return self.alive and not self.battery_absent and self.percentage is not None

    def _get_fill_bucket(self):
        if not self.percentage_known:
            return None

        last_bucket = len(DISCHARGING_GLYPHS) - 1
        fraction = min(max(self.percentage, 0.0), 100.0) / 100

        return round(fraction * last_bucket)

    def _get_glyph(self):
        if self.fill_bucket is None:
            return UNKNOWN_GLYPH

        glyphs = CHARGING_GLYPHS if self.charging else DISCHARGING_GLYPHS

        return glyphs[self.fill_bucket]

    def _get_percent_text(self):
        if not self.percentage_known:
            return UNKNOWN_PERCENT_TEXT

        return f"{self.percentage:.0f} %"

    def _get_tooltip(self):
        if self.level == LEVEL_UNAVAILABLE:
            return "Battery monitor unavailable"

        if self.level == LEVEL_ABSENT:
            return "No battery connected"

        parts = ["Low-voltage alert"] if self.alert else []

        if self.percentage is None:
            parts.append("Battery level unknown")
        else:
            parts.append(f"Battery {self.percentage:.0f} %")

        if self.voltage is not None:
            parts.append(f"{self.voltage:.1f} V")

        if self.current is not None:
            parts.append(f"{abs(self.current):.1f} A")

        parts.append("charging" if self.charging else "discharging")

        if self.charging and self.time_to_full is not None:
            parts.append(f"{_format_duration(self.time_to_full)} to full")

        if not self.charging and self.time_to_empty is not None:
            parts.append(f"{_format_duration(self.time_to_empty)} to empty")

        return " · ".join(parts)
