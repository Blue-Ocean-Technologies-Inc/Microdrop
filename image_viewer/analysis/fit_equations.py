# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fit-equations popup: the equation being fitted, editable, above a
table of every ROI's fitted parameters — one column per parameter of
whatever model is in force. Typing an equation refits on the spot; one
that is neither a built-in nor already saved can be added to the
presets from here."""

# Third-party imports.
import numpy as np

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Str,
    observe,
)
from traitsui.api import (
    EnumEditor,
    Handler,
    HGroup,
    HSplit,
    Item,
    Label,
    TabularEditor,
    UItem,
    VGroup,
    View,
)
from traitsui.tabular_adapter import TabularAdapter

# Local imports.
from .curve_fit import CUSTOM_METHOD, fit_series, trimmed_note
from .fit_expression import FitExpressionError, parse_expression
from .fit_presets import (
    add_preset,
    expression_for,
    fit_arguments,
    method_for_expression,
    method_label,
)
from .plot_series import derive_series

#: Column widths as fractions of the viewport; the parameters share
#: what the fixed columns leave, however many of them there are.
_NAME_WIDTH = 0.18
_R_SQUARED_WIDTH = 0.12
_RANGE_WIDTH = 0.16


class FitEquationRow(HasTraits):
    """One ROI's fit outcome: its fitted parameter values in the fit's
    own parameter order, plus how good that fit was."""

    roi_name = Str()
    #: Formatted parameter values, positionally matching the parameter
    #: columns; empty when the fit failed.
    values = List(Str)
    r_squared_text = Str()
    fit_range_text = Str()
    #: Why there are no values, shown under the first parameter.
    note = Str()
    #: The user's starting values were given but did not converge.
    auto_seeded = Bool(False)


class _FitAdapter(TabularAdapter):
    """The parameter columns are rebuilt per fit, so their text comes
    from the row's own list by position rather than from a named trait
    per column."""

    can_edit = False

    #: How many of the middle columns are parameters.
    parameter_count = Int(0)

    #: Widths of the fixed columns, as fractions of the viewport. The
    #: parameter columns take the default share each, there being no
    #: knowing how many of them a typed equation will have.
    roi_name_width = Float(_NAME_WIDTH)
    r_squared_width = Float(_R_SQUARED_WIDTH)
    fit_range_width = Float(_RANGE_WIDTH)

    def get_text(self, object, trait, row, column):
        item = getattr(object, trait)[row]
        if column == 0:
            return item.roi_name
        if column == self.parameter_count + 1:
            return item.r_squared_text
        if column > self.parameter_count + 1:
            return item.fit_range_text
        index = column - 1
        if item.values:
            return item.values[index] if index < len(item.values) else ""
        # A failed fit says so once, under the first parameter, rather
        # than leaving a row of blanks that reads like zeros.
        return item.note if index == 0 else ""


def fit_rows(session, filtered_paths, presets):
    """(parameter names, rows) for the session's current fit over the
    filtered images. The names come from the first ROI that fitted:
    every ROI is fitted with the same model, so they all report the
    same parameters in the same order."""
    method, expression = fit_arguments(session.figure, presets)
    parameters, rows = [], []
    for roi_id, (name, elapsed, values) in derive_series(
        session, filtered_paths
    ).items():
        fit = fit_series(
            elapsed,
            values,
            method,
            session.figure.trim_poor_fit,
            expression,
            session.figure.initial_guesses,
        )
        row = FitEquationRow(roi_name=name)
        if fit is None:
            row.note = "no fit selected" if method == "none" else "fit failed"
        else:
            if not parameters:
                parameters = list(fit.params)
            row.values = [f"{value:.4g}" for value in fit.params.values()]
            row.r_squared_text = f"{fit.r_squared:.4f}"
            row.auto_seeded = fit.auto_seeded
            finite_t = np.asarray(elapsed, dtype=float)[
                np.isfinite(np.asarray(values, dtype=float))
            ]
            row.fit_range_text = trimmed_note(fit, finite_t.max()).strip(" ()")
        rows.append(row)
    return parameters, rows


class GuessRow(HasTraits):
    """One parameter's starting value, as text so that empty can mean
    "seed this automatically" rather than zero."""

    name = Str()
    text = Str()

    def value(self):
        """The number typed, or None when it is blank or not one."""
        try:
            return float(self.text)
        except ValueError:
            return None


class _GuessAdapter(TabularAdapter):
    columns = [("Parameter", "name"), ("Start value", "text")]
    name_width = Float(0.45)
    text_width = Float(0.55)

    def get_can_edit(self, object, trait, row):
        return self.columns[self.column][1] == "text"


class _FitEquationsHandler(Handler):
    """Keeps the two table widgets to hand so a refit can force them to
    repaint in full."""

    def init(self, info):
        controls = [
            editor.control for editor in (info.rows, info.guesses) if editor is not None
        ]
        for control in controls:
            # Opaque, so a repaint clears what it draws over instead of
            # letting the previous frame show through the new text.
            control.viewport().setAutoFillBackground(True)
        info.object._table_controls = controls
        return True


class PresetName(HasTraits):
    """Modal asking what to call the equation being saved."""

    name = Str()

    traits_view = View(
        Item("name", label="Preset name"),
        title="Save fit equation",
        buttons=["OK", "Cancel"],
        kind="livemodal",
        width=280,
    )


class FitEquationsTable(HasTraits):
    """View-model for the popup: the fit in force, editable, and one
    row per ROI. Live — changing the equation refits every ROI."""

    #: Set by the pane; both are read, never written, except for the
    #: figure's fit settings which this popup exists to change.
    session = Instance(HasTraits)
    model = Instance(HasTraits)
    filtered_paths = List(Str)

    rows = List(FitEquationRow)
    adapter = Instance(TabularAdapter)

    #: One per parameter of the current fit; blank text = seed it
    #: automatically. Only a complete set is used (see user_seed).
    guesses = List(GuessRow)

    #: The equation as typed, and why it cannot be used ('' when fine).
    expression = Str()
    error = Str()

    add_preset_button = Button("Add to presets")
    can_add_preset = Bool(False)
    seed_from_fit_button = Button("Seed from fit")
    clear_guesses_button = Button("Auto")

    #: Set while one of the two-way observers below is writing the
    #: other's trait, so the dropdown and the field cannot chase each
    #: other around.
    _syncing = Bool(False)

    #: Parameter names of the current fit, in fitted order.
    _parameters = List(Str)

    #: The two table widgets, handed over by the handler once they
    #: exist — a refit has to repaint them itself (see _repaint_tables).
    _table_controls = List()

    def _adapter_default(self):
        return _FitAdapter()

    def default_traits_view(self):
        # Built per instance: the TabularEditor holds its adapter by
        # value, and this popup's columns change with the fit.
        return View(
            HGroup(
                Item(
                    "object.session.figure.fit_method",
                    label="Fit",
                    editor=EnumEditor(
                        name="object.model.fit_method_choices",
                        format_func=self._method_label,
                    ),
                ),
                UItem(
                    "add_preset_button",
                    enabled_when="can_add_preset",
                    tooltip="Save this equation as a preset you can "
                    "pick from the Fit list",
                ),
            ),
            HGroup(
                Label("F(x) = "),
                UItem(
                    "expression",
                    springy=True,
                    tooltip="Any equation in x — every other symbol "
                    "is a fitted parameter, e.g. "
                    "a + b*exp(-c*x)",
                ),
            ),
            UItem("error", style="readonly", visible_when="error != ''"),
            HSplit(
                VGroup(
                    HGroup(
                        UItem(
                            "seed_from_fit_button",
                            enabled_when="len(guesses) > 0",
                            tooltip="Fill the starting values with "
                            "what the fit just found, to "
                            "nudge from there",
                        ),
                        UItem(
                            "clear_guesses_button",
                            tooltip="Clear them and let the fit "
                            "choose its own starting values",
                        ),
                    ),
                    UItem(
                        "guesses",
                        editor=TabularEditor(
                            adapter=_GuessAdapter(), editable=True, auto_update=True
                        ),
                    ),
                    label="Start values",
                    show_border=True,
                ),
                UItem(
                    "rows",
                    editor=TabularEditor(
                        adapter=self.adapter, editable=False, stretch_last_section=False
                    ),
                ),
            ),
            title="Fit equations",
            width=760,
            height=340,
            resizable=True,
            handler=_FitEquationsHandler(),
        )

    def _method_label(self, key):
        return method_label(key, self.model.fit_presets)

    # ------------------------------------------------------------------ #
    # Two-way sync: the dropdown fills the field, and editing the field  #
    # switches the method to whatever now matches it.                     #
    # ------------------------------------------------------------------ #
    @observe("session:figure:fit_method")
    def _on_method_changed(self, event):
        if self._syncing:
            return
        self.reload()

    def reload(self):
        """Show the fit currently in force, equation and all. Also how
        the popup opens: nothing has changed at that point, so there is
        no notification to ride, and the field would sit empty until
        the user touched something."""
        self._syncing = True
        try:
            self.expression = expression_for(
                self.session.figure.fit_method,
                self.model.fit_presets,
                self.session.figure.custom_expression,
            )
            self.error = ""
        finally:
            self._syncing = False
        self._update_can_add()
        self.refresh()

    @observe("expression")
    def _on_expression_changed(self, event):
        self._update_can_add()
        if self._syncing or not self.expression.strip():
            return
        try:
            parse_expression(self.expression)
        except FitExpressionError as error:
            # Say what is wrong and leave the previous fit standing:
            # every keystroke passes through here, and most of them are
            # halfway through an equation.
            self.error = str(error)
            return
        self.error = ""
        self._syncing = True
        try:
            figure = self.session.figure
            figure.custom_expression = self.expression
            figure.fit_method = (
                method_for_expression(self.expression, self.model.fit_presets)
                or CUSTOM_METHOD
            )
        finally:
            self._syncing = False
        self.refresh()

    def _update_can_add(self):
        text = self.expression.strip()
        self.can_add_preset = (
            bool(text)
            and not method_for_expression(text, self.model.fit_presets)
            and _parses(text)
        )

    @observe("add_preset_button")
    def _add_preset(self, event):
        entry = PresetName()
        if not entry.edit_traits().result or not entry.name.strip():
            return
        name = entry.name.strip()
        self.model.fit_presets = add_preset(
            list(self.model.fit_presets), name, self.expression.strip()
        )
        self._syncing = True
        try:
            self.session.figure.fit_method = f"preset:{name}"
        finally:
            self._syncing = False
        self._update_can_add()

    # ------------------------------------------------------------------ #
    # Starting values                                                     #
    # ------------------------------------------------------------------ #
    @observe("guesses:items:text")
    def _on_guess_edited(self, event):
        """Store what is typed and refit. A partial set is kept as
        typed — the fit falls back to its own seeds until every
        parameter has one, which is what the hint says."""
        if self._syncing:
            return
        self.session.figure.initial_guesses = {
            row.name: row.value() for row in self.guesses if row.value() is not None
        }
        self.refresh()

    @observe("seed_from_fit_button")
    def _seed_from_fit(self, event):
        """Fill every starting value from the fit just made, so the
        user nudges from where it landed instead of typing a whole
        vector from nothing."""
        fitted = self._fitted_parameters()
        if not fitted:
            return
        self._syncing = True
        try:
            for row in self.guesses:
                if row.name in fitted:
                    row.text = f"{fitted[row.name]:.6g}"
        finally:
            self._syncing = False
        self._on_guess_edited(None)

    @observe("clear_guesses_button")
    def _clear_guesses(self, event):
        self._syncing = True
        try:
            for row in self.guesses:
                row.text = ""
        finally:
            self._syncing = False
        self.session.figure.initial_guesses = {}
        self.refresh()

    def _fitted_parameters(self):
        """The first ROI's fitted values, by name — the natural seed to
        offer, every ROI being fitted with the same model."""
        for row in self.rows:
            if row.values:
                return {
                    name: float(value)
                    for name, value in zip(self._parameters, row.values)
                }
        return {}

    # ------------------------------------------------------------------ #
    def refresh(self):
        """Refit every ROI and rebuild the table around the parameters
        the fit reports."""
        parameters, rows = fit_rows(
            self.session, self.filtered_paths, self.model.fit_presets
        )
        show_range = any(row.fit_range_text for row in rows)
        self.adapter.parameter_count = len(parameters)
        columns = [("ROI", "roi_name")]
        columns += [(name, f"p{index}") for index, name in enumerate(parameters)]
        columns.append(("R²", "r_squared"))
        if show_range:
            columns.append(("Fitted to", "fit_range"))
        # The editor watches this list, so it is assigned last: the
        # parameter count must be in place before the headers are
        # rebuilt around it.
        self.adapter.columns = columns
        self.rows = rows
        self._parameters = parameters
        self._repaint_tables()
        self._sync_guess_rows(parameters)
        # Reached only with an equation that parsed, so the field is
        # free to report on the fit instead.
        self.error = (
            "Those starting values did not converge — fitted "
            "from automatic ones instead"
            if any(row.auto_seeded for row in rows)
            else ""
        )

    def _repaint_tables(self):
        """Repaint both tables outright after a refit.

        Changing the adapter's columns rebuilds the headers but does
        not reset the model, so the view repaints only the region it
        works out to be dirty — and the columns have just moved under
        it, leaving the old text still painted where the new text now
        lands."""
        for control in self._table_controls:
            control.viewport().update()

    def _sync_guess_rows(self, parameters):
        """One row per parameter of the current fit, keeping whatever
        was already typed for a parameter of the same name (editing an
        equation usually keeps most of its parameters)."""
        if [row.name for row in self.guesses] == list(parameters):
            # Same parameters: leave the rows themselves alone. Every
            # keystroke refits, and replacing the list under the editor
            # would take the cursor out of the cell being typed in.
            return
        typed = {row.name: row.text for row in self.guesses}
        stored = self.session.figure.initial_guesses
        self._syncing = True
        try:
            self.guesses = [
                GuessRow(
                    name=name,
                    text=typed.get(name)
                    or (f"{stored[name]:.6g}" if name in stored else ""),
                )
                for name in parameters
            ]
        finally:
            self._syncing = False


def _parses(text):
    try:
        parse_expression(text)
    except FitExpressionError:
        return False
    return True
