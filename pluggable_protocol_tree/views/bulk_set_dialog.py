"""Bulk Set Values dialog for the pluggable protocol tree (issue #474).

Lets the user write one or more column values across every selected step in a
single action. Built around a throwaway *template* step row
(``manager.step_type()``): each settable column reuses its own editor widget
(line edit / spin box / combo box) and value plumbing via the column view, so
the dialog never reimplements per-type widgets. Checkbox columns — whose view
has no editor widget — get a plain QCheckBox.

The caller reads back ``values()`` (``{col_id: value}`` for the ticked rows)
and ``apply_nested`` and applies them with ``RowManager.set_values`` /
``steps_under``.
"""

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logger.logger_service import get_logger

logger = get_logger(__name__)


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
        # col_id -> (apply_checkbox, value_reader)
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

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _build_column_row(self, column):
        """Return ``(apply_checkbox, value_widget)`` for a settable column, or
        None for a column that can't be bulk-set.

        Settable = the column view is editable or user-checkable on a step.
        Read-only columns (type, id, derived cells) and group-only columns are
        excluded automatically. Records a value reader in ``self._rows``.
        """
        flags = column.view.get_flags(self._template)
        editable = bool(flags & Qt.ItemIsEditable)
        checkable = bool(flags & Qt.ItemIsUserCheckable)
        if not (editable or checkable):
            return None

        default = column.model.get_value(self._template)
        apply_checkbox = QCheckBox(column.model.col_name)

        if editable:
            value_widget = column.view.create_editor(self, self._template)
            if value_widget is None:
                # Editable flag but no editor widget — nothing to bulk-set.
                return None
            column.view.set_editor_data(value_widget, default)
            reader = (
                lambda col=column, w=value_widget: col.view.get_editor_data(w)
            )
        else:
            # Checkbox column: the view edits via the Qt check role, not an
            # editor widget, so present a plain checkbox seeded with the default.
            value_widget = QCheckBox()
            value_widget.setChecked(bool(default))
            reader = lambda w=value_widget: w.isChecked()

        # The value only matters once the user opts the column in.
        value_widget.setEnabled(False)
        apply_checkbox.toggled.connect(value_widget.setEnabled)

        self._rows[column.model.col_id] = (apply_checkbox, reader)
        return apply_checkbox, value_widget

    def values(self) -> dict:
        """``{col_id: value}`` for every ticked Apply row (others omitted)."""
        return {
            col_id: reader()
            for col_id, (apply_checkbox, reader) in self._rows.items()
            if apply_checkbox.isChecked()
        }

    @property
    def apply_nested(self) -> bool:
        """Whether to recurse into nested groups when expanding selected groups."""
        return self.nested_checkbox.isChecked()
