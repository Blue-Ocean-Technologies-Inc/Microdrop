# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free logic behind the Fill Pattern dialog.

Three concerns, all independent of any widget:

* **Field discovery** — which step cells can carry a numeric pattern, read
  from the active (already compound-expanded) column set: the row trait's
  type decides numeric-ness and Int vs Float, the trait and the cell view
  supply bounds. A compound field whose cell is only editable while sibling
  checkboxes are ticked (the heater's Set Temp, the magnet's Set Magnet)
  records those siblings as *enablers*, found by probing the view's own
  cross-cell ``get_flags(row)`` rule — no column is special-cased.
* **Value generation** — ramps, fitted ramps, and alternating cycles.
* **Applying** — writes through ``RowManager.set_values`` (the Bulk Set
  path: column handlers, lock checks, ``cell_changed``) and inserts new
  steps through ``RowManager.add_step`` seeded with a copy of the anchor
  step, like next-at-end duplication and the add-step topic do.
"""

# Standard library imports.
import math
import re

# Enthought library imports.
from traits.api import (
    BaseBool,
    BaseFloat,
    BaseInt,
    BaseRange,
    Bool,
    Float,
    HasTraits,
    Str,
)
from traits.api import List as ListTrait

# Microdrop package imports.
from pluggable_protocol_tree.consts import STEP_PATTERN_RAMP
from pluggable_protocol_tree.models.row import GroupRow

#: Trailing '(unit)' / '[col_id]' groups stripped from a default group name.
_LABEL_SUFFIX = re.compile(r"(\s*(\([^)]*\)|\[[^\]]*\]))+\s*$")

#: Slack for float division when counting ramp steps (0.3 / 0.1 must be 3).
_RAMP_EPSILON = 1e-9

#: Decimal places kept on generated float values, so 0.1 + 0.2 lands on 0.3.
_VALUE_DECIMALS = 10


class PatternField(HasTraits):
    """One numeric step cell a pattern can target."""

    #: Row attribute / cell col_id the pattern writes.
    col_id = Str()

    #: Label shown in the column picker — the grid's column header.
    label = Str()

    #: True for Int cells: generated values are rounded to whole numbers.
    is_int = Bool(False)

    #: Inclusive bounds a value must sit within (infinite when unbounded).
    low = Float(-math.inf)
    high = Float(math.inf)

    #: Sibling checkbox fields that must be ticked for this cell to act.
    enabler_ids = ListTrait(Str)

    #: Grid labels of ``enabler_ids``, for the dialog summary.
    enabler_labels = ListTrait(Str)


# --- field discovery ---------------------------------------------------------


def _numeric_bounds(trait_type):
    """``(is_int, low, high)`` for a numeric row trait, or None otherwise."""
    if isinstance(trait_type, BaseRange):
        low, high = trait_type._low, trait_type._high

        # A dynamic Range names other traits for its bounds; treat it as open.
        if not isinstance(low, (int, float)):
            low = -math.inf

        if not isinstance(high, (int, float)):
            high = math.inf

        is_int = isinstance(trait_type.default_value, int) and not isinstance(
            trait_type.default_value, bool
        )

        return is_int, float(low), float(high)

    if isinstance(trait_type, BaseBool):
        return None

    if isinstance(trait_type, BaseInt):
        return True, -math.inf, math.inf

    if isinstance(trait_type, BaseFloat):
        return False, -math.inf, math.inf

    return None


def _row_trait_type(step_type, col_id):
    trait = step_type.class_traits().get(col_id)

    return None if trait is None else trait.handler


def _view_bounds(view):
    """Spin-box style ``low``/``high`` hints on a cell view, else open bounds."""
    low = getattr(view, "low", -math.inf)
    high = getattr(view, "high", math.inf)

    if not isinstance(low, (int, float)) or isinstance(low, bool):
        low = -math.inf

    if not isinstance(high, (int, float)) or isinstance(high, bool):
        high = math.inf

    return float(low), float(high)


def _required_enablers(column, checkbox_siblings, step_type, is_editable):
    """Enabler col_ids for ``column``, or None when it is never editable.

    Probes a scratch step: with every sibling checkbox ticked the cell must
    be editable; a sibling is an enabler when unticking it alone makes the
    cell read-only again.
    """
    probe = step_type()

    for sibling in checkbox_siblings:
        setattr(probe, sibling.model.col_id, True)

    if not is_editable(column, probe):
        return None

    enablers = []

    for sibling in checkbox_siblings:
        sibling_id = sibling.model.col_id
        setattr(probe, sibling_id, False)

        if not is_editable(column, probe):
            enablers.append(sibling)

        setattr(probe, sibling_id, True)

    return enablers


def discover_pattern_fields(columns, step_type, is_editable):
    """Return the ``PatternField`` for every numeric, user-editable step cell.

    Parameters
    ----------
    columns : list of IColumn
        The RowManager's column set (compound columns already expanded into
        one Column per field; fields of one compound share ``Column.id``).
    step_type : type
        The RowManager's dynamic step row class — its traits give each
        cell's type and a scratch instance probes editability.
    is_editable : callable
        ``is_editable(column, row) -> bool`` — whether the column's view lets
        the user edit that row's cell. Injected so this module stays Qt-free.
    """
    fields = []

    for column in columns:
        col_id = column.model.col_id
        numeric = _numeric_bounds(_row_trait_type(step_type, col_id))

        if numeric is None:
            continue

        checkbox_siblings = [
            sibling
            for sibling in columns
            if sibling is not column
            and sibling.id == column.id
            and isinstance(_row_trait_type(step_type, sibling.model.col_id), BaseBool)
        ]
        enablers = _required_enablers(column, checkbox_siblings, step_type, is_editable)

        if enablers is None:
            continue

        is_int, trait_low, trait_high = numeric
        view_low, view_high = _view_bounds(column.view)
        fields.append(
            PatternField(
                col_id=col_id,
                label=column.model.col_name or col_id,
                is_int=is_int,
                low=max(trait_low, view_low),
                high=min(trait_high, view_high),
                enabler_ids=[e.model.col_id for e in enablers],
                enabler_labels=[e.model.col_name or e.model.col_id for e in enablers],
            )
        )

    _disambiguate_labels(fields)

    return fields


def _disambiguate_labels(fields):
    """Suffix duplicate picker labels with their col_id so each is unique."""
    labels = [field.label for field in fields]

    for field in fields:
        if labels.count(field.label) > 1:
            field.label = f"{field.label} [{field.col_id}]"


# --- value generation --------------------------------------------------------


def _tidy(value):
    return round(value, _VALUE_DECIMALS)


def ramp_values(start, stop, increment):
    """Values from ``start`` toward ``stop`` in steps of ``increment``.

    The direction follows ``stop - start``. When ``increment`` does not divide
    the span evenly, ``stop`` is appended as a final, shorter step, so the
    ramp always ends exactly on ``stop`` and never overshoots it.
    """
    if increment <= 0:
        raise ValueError("Increment must be greater than zero.")

    span = stop - start
    step = math.copysign(increment, span)
    count = math.floor(abs(span) / increment + _RAMP_EPSILON) + 1
    values = [_tidy(start + i * step) for i in range(count)]

    if not math.isclose(values[-1], stop, abs_tol=_RAMP_EPSILON):
        values.append(_tidy(stop))

    return values


def ramp_lands_on_stop(start, stop, increment):
    """True when ``increment`` divides the ramp span evenly (no clamped step)."""
    steps = abs(stop - start) / increment

    return math.isclose(steps, round(steps), abs_tol=_RAMP_EPSILON)


def fit_increment(start, stop, count):
    """Increment that spreads ``start``..``stop`` over ``count`` steps."""
    if count < 2:
        return 0.0

    return (stop - start) / (count - 1)


def fit_ramp_values(start, stop, count):
    """``count`` evenly spaced values from ``start`` to ``stop`` inclusive."""
    increment = fit_increment(start, stop, count)
    values = [_tidy(start + i * increment) for i in range(count)]

    if values:
        values[-1] = _tidy(stop)

    return values


def alternate_values(pattern, count):
    """``pattern`` cycled to ``count`` values."""
    return [pattern[i % len(pattern)] for i in range(count)]


def parse_values(text):
    """Parse a comma/space separated list of numbers.

    Raises ValueError naming the first entry that is not a number.
    """
    values = []

    for entry in text.replace(",", " ").split():
        try:
            values.append(float(entry))
        except ValueError:
            raise ValueError(f"'{entry}' is not a number.") from None

    return values


def coerce_values(values, is_int):
    """Round to whole numbers for Int cells; Float cells keep their decimals."""
    if is_int:
        return [int(round(value)) for value in values]

    return list(values)


def bounds_error(values, field):
    """Message for the first value outside ``field``'s bounds, else ''."""
    for value in values:
        if field.low <= value <= field.high:
            continue

        return (
            f"{format_value(value)} is outside the {field.label} range "
            f"{format_value(field.low)} to {format_value(field.high)}."
        )

    return ""


def format_value(value):
    """Compact display of a pattern value (no trailing zeros)."""
    return f"{value:g}"


def default_group_name(field_label, mode):
    """Suggested name for a group of created steps, e.g. 'Target Temp ramp'.

    The label's trailing unit / col_id suffixes ('(°C)', '[col_id]') are
    dropped; a ramp is a 'ramp', any other pattern a 'pattern'.
    """
    base = _LABEL_SUFFIX.sub("", field_label or "").strip() or "Step"
    kind = "ramp" if mode == STEP_PATTERN_RAMP else "pattern"

    return f"{base} {kind}"


# --- applying to the tree ----------------------------------------------------


def selected_steps_in_order(manager):
    """The selected steps (groups expanded one level, as Bulk Set does) in
    tree order — Qt reports selections in click order, not row order."""
    return sorted(manager.steps_under([tuple(p) for p in manager.selection]))


def last_step_path(manager):
    """Path of the last step in tree order, or None when there is none."""
    steps = [row for row in manager.iter_all_rows() if not isinstance(row, GroupRow)]

    return tuple(steps[-1].path) if steps else None


def apply_pattern_to_steps(manager, paths, field, values):
    """Write ``values`` onto the existing steps at ``paths``, pairwise.

    Enabler checkboxes are ticked first so the pattern is not inert. Steps
    sharing a value are written in one ``set_values`` batch, so a column
    handler that prompts does so once per distinct value, not per row.
    """
    for enabler_id in field.enabler_ids:
        manager.set_values(paths, enabler_id, True)

    paths_by_value = {}

    for path, value in zip(paths, values):
        paths_by_value.setdefault(value, []).append(path)

    for value, value_paths in paths_by_value.items():
        manager.set_values(value_paths, field.col_id, value)


def step_copy_values(manager, row):
    """Every column value of ``row`` — the ``add_step`` seed for a copy."""
    return {
        column.model.col_id: getattr(row, column.model.col_id)
        for column in manager.columns
        if hasattr(row, column.model.col_id)
    }


def insert_pattern_steps(manager, anchor_path, field, values, group_name=""):
    """Insert one new step per value, each a copy of the anchor step.

    The new steps go right after ``anchor_path`` in its group, or at the end
    of the protocol when ``anchor_path`` is None (then seeded from the last
    step, if any). With a ``group_name``, a new group of that name takes that
    position instead and the steps become its children, in order. Returns the
    new steps' paths.
    """
    seed_path = anchor_path if anchor_path is not None else last_step_path(manager)
    seed = (
        {}
        if seed_path is None
        else step_copy_values(manager, manager.get_row(seed_path))
    )

    for enabler_id in field.enabler_ids:
        seed[enabler_id] = True

    if anchor_path is None:
        parent_path, first_index = (), len(manager.root.children)
    else:
        parent_path, first_index = anchor_path[:-1], anchor_path[-1] + 1

    if group_name:
        parent_path = manager.add_group(
            parent_path=parent_path, index=first_index, name=group_name
        )
        first_index = 0

    new_paths = []

    for offset, value in enumerate(values):
        new_path = manager.add_step(
            parent_path=parent_path,
            index=first_index + offset,
            values={**seed, field.col_id: value},
        )
        _run_row_loaded_hooks(manager, manager.get_row(new_path))
        new_paths.append(new_path)

    return new_paths


def _run_row_loaded_hooks(manager, row):
    """Rebuild runtime-derived column state (issue #541 locks and the like)
    that ``add_step``'s bare setattr skips — as the add-step topic does."""
    for column in manager.columns:
        hook = getattr(column.model, "on_row_loaded", None)

        if hook is not None:
            hook(row)
