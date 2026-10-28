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
    SOC_SOURCE_TEXTS,
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


def _int_or_none(value):
    """Return ``value`` when it is an int, or None otherwise."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value

    return None


def _text_or_empty(value):
    """Return ``value`` when it is a string, or "" otherwise."""
    return value if isinstance(value, str) else ""


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

    The ``*_text`` properties are the details-panel rows, each "" while its
    value is unknown.
    """

    #: State of charge in percent (0-100); None while unknown.
    percentage = Union(None, Float)

    #: Pack voltage (V); None while unknown.
    voltage = Union(None, Float)

    #: Voltage per cell (V); None while unknown.
    voltage_per_cell = Union(None, Float)

    #: Pack current (A), positive while discharging; None while unknown.
    current = Union(None, Float)

    #: Pack power (W), positive while discharging; None while unknown.
    power = Union(None, Float)

    #: Estimated seconds until empty (snapshot key time_to_empty_s); None
    #: while unknown or charging.
    time_to_empty = Union(None, Float)

    #: Estimated seconds until full (snapshot key time_to_full_s); None
    #: while unknown or discharging.
    time_to_full = Union(None, Float)

    #: Charge left in the pack (Ah); None while unknown.
    remaining_ah = Union(None, Float)

    #: The daemon's state word, e.g. "Charging" or "Idle"; "" while unknown.
    state = Str()

    #: Cells in series; None while unknown.
    cells = Union(None, Int)

    #: Pack chemistry, e.g. "li-ion"; "" while unknown.
    chemistry = Str()

    #: How the daemon estimates the state of charge: "voltage", "coulomb"
    #: or "blend"; "" while unknown.
    soc_source = Str()

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

    #: Why there are no readings to show ("Battery monitor unavailable",
    #: "No battery connected"); "" while there are.
    headline = Property(Str, observe="level")

    #: State of charge row, e.g. "34 %", or "Unknown".
    charge_text = Property(Str, observe=["percentage_known", "percent_text"])

    #: Voltage row, e.g. "23.6 V (3.94 V/cell)".
    voltage_text = Property(Str, observe=["voltage", "voltage_per_cell"])

    #: Current row with its direction, e.g. "5.9 A into the pack".
    current_text = Property(Str, observe="current")

    #: Power row, e.g. "139 W"; the direction is on the current row.
    power_text = Property(Str, observe="power")

    #: State row: the daemon's state word, flagged while the alert is raised.
    state_text = Property(Str, observe=["state", "alert"])

    #: Time row, e.g. "11 h 03 min to full" while charging.
    time_text = Property(Str, observe=["charging", "time_to_empty", "time_to_full"])

    #: Pack row, e.g. "6 cells · li-ion · 34.5 Ah left".
    pack_text = Property(Str, observe=["cells", "chemistry", "remaining_ah"])

    #: Estimate row: how the state of charge is worked out.
    source_text = Property(Str, observe="soc_source")

    #: Plain-text details for the icon's tooltip.
    tooltip = Property(
        Str,
        observe=[
            "headline",
            "alert",
            "percentage",
            "voltage",
            "current",
            "charging",
            "time_text",
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
            voltage_per_cell=_number_or_none(snapshot.get("voltage_per_cell")),
            current=_number_or_none(snapshot.get("current")),
            power=_number_or_none(snapshot.get("power")),
            time_to_empty=_duration_or_none(snapshot.get("time_to_empty_s")),
            time_to_full=_duration_or_none(snapshot.get("time_to_full_s")),
            remaining_ah=_duration_or_none(snapshot.get("remaining_ah")),
            state=_text_or_empty(snapshot.get("state")),
            cells=_int_or_none(snapshot.get("cells")),
            chemistry=_text_or_empty(snapshot.get("chemistry")),
            soc_source=_text_or_empty(snapshot.get("soc_source")),
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

    def _get_headline(self):
        if self.level == LEVEL_UNAVAILABLE:
            return "Battery monitor unavailable"

        if self.level == LEVEL_ABSENT:
            return "No battery connected"

        return ""

    def _get_charge_text(self):
        return self.percent_text if self.percentage_known else "Unknown"

    def _get_voltage_text(self):
        if self.voltage is None:
            return ""

        if self.voltage_per_cell is None:
            return f"{self.voltage:.1f} V"

        return f"{self.voltage:.1f} V ({self.voltage_per_cell:.2f} V/cell)"

    def _get_current_text(self):
        if self.current is None:
            return ""

        amps = round(self.current, 1)

        if amps == 0:
            return "0.0 A"

        direction = "draw" if amps > 0 else "into the pack"

        return f"{abs(amps):.1f} A {direction}"

    def _get_power_text(self):
        if self.power is None:
            return ""

        return f"{abs(self.power):.0f} W"

    def _get_state_text(self):
        if not self.alert:
            return self.state

        if not self.state:
            return "Low-voltage alert"

        return f"{self.state} — low-voltage alert"

    def _get_time_text(self):
        if self.charging and self.time_to_full is not None:
            return f"{_format_duration(self.time_to_full)} to full"

        if not self.charging and self.time_to_empty is not None:
            return f"{_format_duration(self.time_to_empty)} to empty"

        return ""

    def _get_pack_text(self):
        parts = []

        if self.cells is not None:
            noun = "cell" if self.cells == 1 else "cells"
            parts.append(f"{self.cells} {noun}")

        if self.chemistry:
            parts.append(self.chemistry)

        if self.remaining_ah is not None:
            parts.append(f"{self.remaining_ah:.1f} Ah left")

        return " · ".join(parts)

    def _get_source_text(self):
        return SOC_SOURCE_TEXTS.get(self.soc_source, self.soc_source)

    def _get_tooltip(self):
        if self.headline:
            return self.headline

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

        if self.time_text:
            parts.append(self.time_text)

        return " · ".join(parts)
