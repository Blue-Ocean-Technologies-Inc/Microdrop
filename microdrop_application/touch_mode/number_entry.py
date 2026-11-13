# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The number pad's model: the typed text, its value and whether it fits the
range. Qt-free, so the keypad logic is testable on its own."""

# Enthought library imports.
from traits.api import Bool, Float, HasTraits, Int, Property, Str

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import DOUBLE_SPINBOX_UNBOUNDED_MAX

# Local imports.
from .consts import NUMBER_ENTRY_MAX_DIGITS, UNBOUNDED_TEXT


def format_number(value, decimals):
    """Format ``value`` with at most ``decimals`` places, dropping trailing
    zeros (``0.50`` shows as ``0.5``, ``200.0`` as ``200``)."""

    if abs(value) >= DOUBLE_SPINBOX_UNBOUNDED_MAX:
        return UNBOUNDED_TEXT if value > 0 else f"-{UNBOUNDED_TEXT}"

    text = f"{value:.{decimals}f}"

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return "0" if text == "-0" else text


class NumberEntry(HasTraits):
    """A number typed on a keypad, checked against a range."""

    #: The typed text: digits, an optional leading "-" and at most one ".".
    text = Str()

    #: Inclusive range the value must fall in.
    minimum = Float()
    maximum = Float()

    #: Digits allowed after the point; 0 makes the entry integer-only.
    decimals = Int(0)

    #: The text is the initial value, shown selected: the next digit
    #: replaces it rather than appending.
    replace_pending = Bool(False)

    #: The typed number, or None while the text is not one.
    value = Property(observe="text")

    #: Whether the typed number lies inside the range.
    in_range = Property(observe="value, minimum, maximum")

    #: Whether the text is a number outside the range: an error to show,
    #: unlike an incomplete entry ("", "-").
    out_of_range = Property(observe="value, in_range")

    #: Whether "." may be typed at all, and whether "-" may.
    allows_point = Property(observe="decimals")
    allows_negative = Property(observe="minimum")

    def start(self, value):
        """Show ``value`` as the initial, selected entry."""
        self.text = format_number(value, self.decimals)
        self.replace_pending = True

    def type_digit(self, digit):
        """Append ``digit``, replacing the initial value if still selected."""

        if self.replace_pending:
            self.text = ""
            self.replace_pending = False

        sign = "-" if self.text.startswith("-") else ""
        unsigned = self.text.removeprefix("-")
        whole, point, fraction = unsigned.partition(".")

        if point and len(fraction) >= self.decimals:
            return

        if len((whole + fraction).lstrip("0")) >= NUMBER_ENTRY_MAX_DIGITS:
            return

        if not point and whole == "0":
            unsigned = digit
        else:
            unsigned += digit

        self.text = f"{sign}{unsigned}"

    def type_point(self):
        """Start the fraction, with a leading zero when nothing is typed."""

        if not self.allows_point:
            return

        if self.replace_pending:
            self.text = ""
            self.replace_pending = False

        if "." in self.text:
            return

        if self.text in ("", "-"):
            self.text += "0"

        self.text += "."

    def toggle_sign(self):
        """Flip the sign, keeping the digits typed so far."""

        if not self.allows_negative:
            return

        self.replace_pending = False

        if self.text.startswith("-"):
            self.text = self.text[1:]
        else:
            self.text = f"-{self.text}"

    def backspace(self):
        """Delete the last character; a selected initial value goes whole."""

        if self.replace_pending:
            self.clear()
        else:
            self.text = self.text[:-1]

    def clear(self):
        """Empty the entry."""
        self.text = ""
        self.replace_pending = False

    def range_text(self, prefix="", suffix=""):
        """Return the range as "30 – 200 V", with the field's affixes."""
        low = format_number(self.minimum, self.decimals)
        high = format_number(self.maximum, self.decimals)

        return f"{prefix}{low} – {prefix}{high}{suffix}"

    def _get_value(self):
        try:
            return float(self.text)
        except ValueError:
            return None

    def _get_in_range(self):
        return self.value is not None and self.minimum <= self.value <= self.maximum

    def _get_out_of_range(self):
        return self.value is not None and not self.in_range

    def _get_allows_point(self):
        return self.decimals > 0

    def _get_allows_negative(self):
        return self.minimum < 0
