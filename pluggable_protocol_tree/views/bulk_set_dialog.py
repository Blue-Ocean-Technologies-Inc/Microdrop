# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Bulk Set Values dialog for the pluggable protocol tree (issue #474).

Lets the user write one or more column values across every selected step in a
single action. Built around a throwaway *template* step row
(``manager.step_type()``): each settable column reuses its own editor widget
(line edit / spin box / combo box, with the view's bounds and decimals) and
value plumbing via the column view, so the dialog never reimplements per-type
widgets. Bool columns — edited in the tree through the Qt check role, so their
view has no editor widget — get an Off/On combo box: each row's Apply tick is
already a checkbox, and a second one beside it reads as a single control.

The caller reads back ``values()`` (``{col_id: value}`` for the ticked rows)
and ``apply_nested`` and applies them with ``RowManager.set_values`` /
``steps_under``.
"""

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from traits.api import BaseBool, BaseEnum, BaseFloat, BaseInt, BaseRange

# Microdrop package imports.
from pluggable_protocol_tree.models._compound_adapters import _CompoundFieldAdapter

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Trait types a compound field can carry and still take a single bulk value.
SCALAR_TRAIT_TYPES = (BaseBool, BaseInt, BaseFloat, BaseEnum, BaseRange)

#: Choices of a Bool column's value combo box, indexed by the bool.
BOOL_CHOICES = ("Off", "On")


def _trait_type(column):
    """Return the class of the trait ``column`` contributes to a row."""
    trait = column.model.trait_for_row()

    return trait if isinstance(trait, type) else type(trait)


class BulkSetDialog(QDialog):
    """Pick one or more column values to apply across the selected steps.

    Args:
        manager: the RowManager — supplies the column set and a template step
            row for seeding editors / resolving editor bounds.
        parent: parent QWidget.
    """

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Set Values")
        self._manager = manager
        # A default step row: the editor context (row-dependent bounds read it)
        # and the source of each column's seed value.
        self._template = manager.step_type()
        # col_id -> (apply_checkbox, value_widget, value_reader)
        self._rows = {}

        outer = QVBoxLayout(self)

        intro = QLabel(
            "Tick the parameters to set and choose their values. They are "
            "applied to every selected step."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setColumnStretch(1, 1)
        row = 0
        for column in manager.columns:
            built = self._build_column_row(column)
            if built is None:
                continue
            apply_checkbox, value_widget = built
            grid.addWidget(apply_checkbox, row, 0)
            grid.addWidget(value_widget, row, 1)
            row += 1

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)
        outer.addWidget(scroll, 1)

        self.nested_checkbox = QCheckBox("Apply to all nested groups")
        outer.addWidget(self.nested_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _is_settable(self, column):
        """Whether ``column`` can be bulk-set on a step.

        Settable = the column view is editable or user-checkable on a step, so
        read-only columns (type, id, derived cells) and group-only columns are
        excluded. A compound field cell may gate its editability on a sibling
        field of the row (e.g. a setpoint locked while its enable checkbox is
        off), which the default template reads as locked. A bulk write spans
        rows whose sibling state differs, so every scalar compound field is
        offered whatever the template says.
        """
        flags = column.view.get_flags(self._template)

        if flags & (Qt.ItemIsEditable | Qt.ItemIsUserCheckable):
            return True

        return isinstance(column.model, _CompoundFieldAdapter) and issubclass(
            _trait_type(column), SCALAR_TRAIT_TYPES
        )

    def _is_check_column(self, column):
        """Whether ``column`` is edited through the Qt check role rather than
        an editor widget — checkable on the template, or Bool-typed and gated
        off it."""
        flags = column.view.get_flags(self._template)

        return bool(flags & Qt.ItemIsUserCheckable) or issubclass(
            _trait_type(column), BaseBool
        )

    def _build_column_row(self, column):
        """Return ``(apply_checkbox, value_widget)`` for a settable column, or
        None for a column that can't be bulk-set. Records the row in
        ``self._rows``.
        """
        if not self._is_settable(column):
            return None

        default = column.model.get_value(self._template)

        if self._is_check_column(column):
            value_widget = QComboBox()
            value_widget.addItems(BOOL_CHOICES)
            value_widget.setCurrentIndex(int(bool(default)))
            reader = partial(self._read_bool, value_widget)
        else:
            value_widget = column.view.create_editor(self, self._template)

            if value_widget is None:
                # A view without an editor widget has nothing to bulk-set.
                return None

            column.view.set_editor_data(value_widget, default)
            reader = partial(column.view.get_editor_data, value_widget)

        apply_checkbox = QCheckBox(column.model.col_name)

        # The value only matters once the user opts the column in.
        value_widget.setEnabled(False)
        apply_checkbox.toggled.connect(value_widget.setEnabled)

        self._rows[column.model.col_id] = (apply_checkbox, value_widget, reader)

        return apply_checkbox, value_widget

    @staticmethod
    def _read_bool(combo):
        """Read a Bool column's Off/On combo box back as a bool."""
        return bool(combo.currentIndex())

    def values(self) -> dict:
        """``{col_id: value}`` for every ticked Apply row (others omitted)."""
        return {
            col_id: reader()
            for col_id, (apply_checkbox, _value_widget, reader) in self._rows.items()
            if apply_checkbox.isChecked()
        }

    @property
    def apply_nested(self) -> bool:
        """Whether to recurse into nested groups when expanding selected groups."""
        return self.nested_checkbox.isChecked()
