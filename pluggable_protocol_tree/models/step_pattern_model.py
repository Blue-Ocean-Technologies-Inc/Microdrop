# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state for the Fill Pattern dialog.

Holds the user's choices (target field, Ramp/Alternate, their parameters)
and keeps a live preview — the generated ``values``, a ``summary`` line,
and ``is_valid`` gating OK — recomputed on every change. With two or more
steps selected the pattern *fits* onto them; otherwise it *creates* new
steps.
"""

# Enthought library imports.
from traits.api import (
    Bool,
    Dict,
    Enum,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
    observe,
)

# Microdrop package imports.
from pluggable_protocol_tree.consts import (
    STEP_PATTERN_ALTERNATE,
    STEP_PATTERN_DEFAULT_CREATE_COUNT,
    STEP_PATTERN_MAX_STEPS,
    STEP_PATTERN_MODES,
    STEP_PATTERN_RAMP,
)
from pluggable_protocol_tree.services.step_pattern import (
    PatternField,
    alternate_values,
    bounds_error,
    coerce_values,
    fit_increment,
    fit_ramp_values,
    format_value,
    parse_values,
    ramp_lands_on_stop,
    ramp_values,
)

#: Traits whose change re-runs the preview.
_PREVIEW_INPUTS = (
    "field_label, mode, start, stop, increment, alternate_text, create_count, fit_count"
)


class StepPatternModel(HasTraits):
    """Choices and live preview of one Fill Pattern run."""

    #: Numeric step fields the pattern can target.
    fields = List(Instance(PatternField))

    #: Picker labels of ``fields``, in order (the Enum's value source).
    field_labels = List(Str)

    #: Label of the targeted field.
    field_label = Enum(values="field_labels")

    #: The targeted field.
    field = Property(Instance(PatternField), observe="field_label, fields.items")

    #: Current value of each field on the steps the pattern starts from —
    #: the fitted steps, or the anchor step — in tree order: {col_id: [v, ...]}.
    current_values = Dict(Str, List)

    #: Number of selected steps; two or more means fit onto them.
    fit_count = Int(0)

    #: True when the pattern fits onto the selection rather than creating steps.
    is_fit = Property(Bool, observe="fit_count")

    mode = Enum(*STEP_PATTERN_MODES)

    #: Ramp: first value.
    start = Float(0.0)

    #: Ramp: last value.
    stop = Float(0.0)

    #: Ramp, create mode: increment between consecutive new steps.
    increment = Float(1.0)

    #: Ramp, fit mode: the increment the selection count implies (read-only).
    fitted_increment = Property(Float, observe="start, stop, fit_count")

    #: Alternate: the values to cycle, e.g. "50, 80".
    alternate_text = Str()

    #: Alternate, create mode: how many new steps to create.
    create_count = Range(1, STEP_PATTERN_MAX_STEPS, STEP_PATTERN_DEFAULT_CREATE_COUNT)

    #: Generated values, one per affected step (empty while invalid).
    values = List()

    #: Ramp, create mode: True when the last step was clamped onto ``stop``.
    clamped = Bool(False)

    #: What OK will do, or why it cannot.
    summary = Str()

    #: Gates the OK button.
    is_valid = Bool(False)

    # --- property getters ---

    def _get_field(self):
        for field in self.fields:
            if field.label == self.field_label:
                return field

        return None

    def _get_is_fit(self):
        return self.fit_count >= 2

    def _get_fitted_increment(self):
        return fit_increment(self.start, self.stop, self.fit_count)

    # --- reactions ---

    @observe("fields.items")
    def _update_field_labels(self, event):
        self.field_labels = [field.label for field in self.fields]

    @observe("field_label", post_init=True)
    def _prefill_from_current_values(self, event=None):
        """Seed start/stop and the alternate list from the field's current
        values: first and last fitted step, or the anchor step's value."""
        field = self.field
        current = self.current_values.get(field.col_id) if field else None

        if not current:
            return

        self.start = float(current[0])
        self.stop = float(current[-1])
        self.alternate_text = ", ".join(
            format_value(value) for value in dict.fromkeys(current)
        )

    @observe(_PREVIEW_INPUTS, post_init=True)
    def _update_preview(self, event=None):
        try:
            values = self._generate_values()
        except ValueError as error:
            self.values = []
            self.summary = str(error)
            self.is_valid = False

            return

        self.values = values
        self.summary = self._describe(values)
        self.is_valid = True

    def traits_init(self):
        if self.field_labels and self.field_label not in self.field_labels:
            self.field_label = self.field_labels[0]

        self._prefill_from_current_values()
        self._update_preview()

    # --- preview helpers ---

    def _generate_values(self):
        """Values for the affected steps; ValueError with a user-facing
        message when the inputs cannot produce a valid pattern."""
        field = self.field

        if field is None:
            raise ValueError("Pick a column to fill.")

        self.clamped = False

        if self.mode == STEP_PATTERN_RAMP:
            raw = self._ramp_values()
        else:
            raw = self._alternate_values()

        if len(raw) > STEP_PATTERN_MAX_STEPS:
            raise ValueError(
                f"That would make {len(raw)} steps; the limit is "
                f"{STEP_PATTERN_MAX_STEPS}. Use a larger increment."
            )

        values = coerce_values(raw, field.is_int)
        error = bounds_error(values, field)

        if error:
            raise ValueError(error)

        return values

    def _ramp_values(self):
        if self.start == self.stop:
            raise ValueError("Start and stop must differ for a ramp.")

        if self.is_fit:
            return fit_ramp_values(self.start, self.stop, self.fit_count)

        if self.increment <= 0:
            raise ValueError("Increment must be greater than zero.")

        self.clamped = not ramp_lands_on_stop(self.start, self.stop, self.increment)

        return ramp_values(self.start, self.stop, self.increment)

    def _alternate_values(self):
        pattern = parse_values(self.alternate_text)

        if not pattern:
            raise ValueError("Enter at least one value to alternate.")

        count = self.fit_count if self.is_fit else self.create_count

        return alternate_values(pattern, count)

    def _describe(self, values):
        field = self.field

        if self.is_fit:
            action = f"Will set {len(values)} selected steps"
        else:
            action = f"Will create {len(values)} steps"

        if self.mode == STEP_PATTERN_ALTERNATE:
            cycle = ", ".join(
                format_value(v) for v in parse_values(self.alternate_text)
            )
            detail = f"cycling {cycle}"
        elif self.is_fit:
            detail = f"increment {format_value(self.fitted_increment)}"
        else:
            detail = f"increment {format_value(self.increment)}"

            if self.clamped:
                detail += f", last step clamped to {format_value(self.stop)}"

        summary = f"{action}, {detail}."

        if field.is_int:
            summary += " Values are rounded to whole numbers."

        if field.enabler_labels:
            summary += f" Also ticks {', '.join(field.enabler_labels)}."

        return summary
