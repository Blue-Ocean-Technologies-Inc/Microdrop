# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The plugin load records as the notifications drawer's Plugins section:
one row per plugin (state glyph, name, start-up time), the drawer's width,
and the selected plugin's details beneath.

A plain Qt table whose rows are rebuilt from the records whenever they
change, not a TraitsUI table editor: that editor keeps its proxy model in
step with a list that grows by invalidating it, which in the drawer left
every row but the first blank. Runs standalone::

    PluginLoadStatusSectionContents(PluginLoadStatusPanelModel(status=s)).show()
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY

# Local imports.
from .consts import (
    PLUGIN_LOAD_STATE_COLORS,
    PLUGIN_LOAD_STATE_GLYPHS,
    TRACEBACK_STYLE_SHEET,
)
from .load_status_model import PluginLoadStatusPanelModel

#: The table's columns.
COLUMN_STATE, COLUMN_NAME, COLUMN_DURATION = range(3)
HEADERS = ("", "Plugin", "Start-up (s)")

#: Pixel size of the state glyphs.
GLYPH_PIXEL_SIZE = 16

#: Most lines of a failure's traceback shown before the details scroll.
DETAILS_MAX_LINES = 12

_RECORD_ROLE = QtCore.Qt.ItemDataRole.UserRole


def format_duration(seconds):
    """Seconds as a plain number; blank until the start finished."""
    return f"{seconds:.3f}" if seconds else ""


class _RecordsBinding(HasTraits):
    """Rebuilds the table once per burst of record changes, and shows the
    selected record's details."""

    model = Instance(PluginLoadStatusPanelModel)

    view = Any()

    #: Whether a rebuild is queued.
    _queued = Bool(False)

    @observe("model:status:records.items")
    @observe("model:status:records:items:[state, name, duration, error]")
    def _records_changed(self, event):

        if not self._queued:
            self._queued = True
            QtCore.QTimer.singleShot(0, self._rebuild)

    @observe("model:details_text")
    def _show_details(self, event):
        self.view.show_details()

    def _rebuild(self):
        self._queued = False

        if self.model is not None:
            self.view.show_records()


class PluginLoadStatusSectionContents(QtWidgets.QWidget):
    """The records' table over the selected record's details."""

    def __init__(self, model, parent=None):
        super().__init__(parent)

        self.model = model

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 6)
        layout.setSpacing(6)

        self.table = QtWidgets.QTableWidget(0, len(HEADERS), self)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed
        )

        # The name takes the room; the glyph and the time their own.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            COLUMN_STATE, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            COLUMN_NAME, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            COLUMN_DURATION, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.itemSelectionChanged.connect(self._select_from_table)
        layout.addWidget(self.table)

        self.details = QtWidgets.QLabel(self)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.details.setStyleSheet(TRACEBACK_STYLE_SHEET)
        self.details.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self.details)

        self._binding = _RecordsBinding(model=model, view=self)
        self.show_records()
        self.show_details()

    def show_records(self):
        """One row per record, the selected one kept selected."""
        records = list(self.model.status.records)
        glyph_font = QtGui.QFont(ICON_FONT_FAMILY)
        glyph_font.setPixelSize(GLYPH_PIXEL_SIZE)
        selected = self.model.selected

        self.table.blockSignals(True)
        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            glyph = QtWidgets.QTableWidgetItem(PLUGIN_LOAD_STATE_GLYPHS[record.state])
            glyph.setFont(glyph_font)
            glyph.setForeground(QtGui.QColor(PLUGIN_LOAD_STATE_COLORS[record.state]))
            glyph.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            glyph.setToolTip(record.state.capitalize())

            name = QtWidgets.QTableWidgetItem(record.name or record.plugin_id)
            name.setToolTip(record.error or record.plugin_id)

            duration = QtWidgets.QTableWidgetItem(format_duration(record.duration))
            duration.setTextAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            )

            for column, item in enumerate((glyph, name, duration)):
                item.setData(_RECORD_ROLE, row)
                self.table.setItem(row, column, item)

            if record is selected:
                self.table.selectRow(row)

        self.table.blockSignals(False)

    def show_details(self):
        record = self.model.selected
        text = self.model.details_text

        # A traceback is long: its last lines say what failed.
        if record is not None and record.traceback:
            lines = text.splitlines()

            if len(lines) > DETAILS_MAX_LINES:
                text = "\n".join(["…", *lines[-DETAILS_MAX_LINES:]])

        self.details.setText(text)

    def dispose(self):
        """Stop following the records."""
        self._binding.model = None

    def _select_from_table(self):
        rows = {index.row() for index in self.table.selectedIndexes()}
        records = self.model.status.records

        if rows and min(rows) < len(records):
            self.model.selected = records[min(rows)]
