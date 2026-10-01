# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Per-ROI table under the intensity plot: editable name (drives the
plot legend and CSV columns), style editors (color, line, marker,
size), and live stats for the image currently shown in the viewer —
including the instant result right after drawing an ROI. A pure
observer of the shared analysis model, mutating it only from Qt editor
signals (GUI thread). Rebuilds (row count, editors, cell identities) on
structure/style change; value-refreshes (stat cells rewritten in place)
on stats/current-image change — both scheduled onto the next event-loop
turn so nothing mutates the table from inside the emitting Qt signal or
traits notification."""

# Third-party imports.
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

# Microdrop style imports.
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.icons.icons import (
    ICON_VISIBILITY,
    ICON_VISIBILITY_OFF,
)

# Local imports.
from ..scale_bar import area_unit, pixel_area
from .consts import ROI_ALPHA_BOUNDS_PCT
from .plot_series import stat_value


def _visibility_glyph(visible):
    return ICON_VISIBILITY if visible else ICON_VISIBILITY_OFF


#: Value columns after the editors, shown for the current image.
_STAT_COLUMNS = ("mean", "bg_corrected", "median", "min", "max", "count", "area")
#: The eye column's header stays blank, as in the device viewer's
#: alpha sidebar; Name keeps column 0, where the rename handler
#: expects it.
_VISIBLE_COLUMN = 1

#: Ticking this marks the ROI as a background reference — a region
#: holding no signal, whose mean the plot can subtract from every
#: ROI.
_BACKGROUND_REF_COLUMN = 2

#: Point size of the eye glyph, matching the device viewer's own
#: visibility column.
EYE_GLYPH_POINT_SIZE = 15

#: Marker-size spinner's reach (pt): 1 is barely visible, 30
#: swallows the curve it marks.
MARKER_SIZE_BOUNDS_PT = (1.0, 30.0)

_HEADERS = (
    "Name",
    "",
    "Bkg Ref",
    "Alpha",
    "Color",
    "Line",
    "Marker",
    "Size",
) + _STAT_COLUMNS
_LINE_CHOICES = ("solid", "dashed", "dotted", "dashdot")
_MARKER_CHOICES = ("none", ".", "o", "s", "^", "x")

#: Row count/editors/cell identities change — triggers a full rebuild.
_TABLE_STRUCTURE = (
    "session, session:rois.items, "
    "session:rois:items:name, "
    "session:rois:items:is_background_ref, "
    "session:rois:items:style:color, "
    "session:scale:metres_per_pixel, "
    "session:scale:unit"
)
#: Only the stat-cell text can be stale — triggers a values-only
#: refresh. The two geometry clauses close a staleness edge: editing an
#: ROI back to an already-cached geometry never bumps stats_revision.
_TABLE_VALUES = (
    "session:stats_revision, current_image_path, "
    "session:rois:items:geometry, "
    "session:rois:items:overrides.items"
)


class RoiStatsTable(QTableWidget):
    """One row per ROI; editors write straight into the session."""

    def __init__(self, model, parent=None):
        super().__init__(0, len(_HEADERS), parent)
        self._model = model
        self._rebuilding = False
        self._detached = False
        self._pending = None  # None | "rebuild" | "values"
        self.verticalHeader().setVisible(False)
        self.itemChanged.connect(self._on_item_changed)
        self.cellClicked.connect(self._on_cell_clicked)
        model.observe(self._on_structure_changed, _TABLE_STRUCTURE)
        model.observe(self._on_values_changed, _TABLE_VALUES)
        self._rebuild()

    def detach(self):
        # An in-flight coalescing singleShot may fire after the widget's
        # C++ side is gone; the flag makes it a no-op.
        self._detached = True
        self._model.observe(self._on_structure_changed, _TABLE_STRUCTURE, remove=True)
        self._model.observe(self._on_values_changed, _TABLE_VALUES, remove=True)

    def _on_structure_changed(self, event):
        self._schedule("rebuild")

    def _on_values_changed(self, event):
        self._schedule("values")

    def _schedule(self, kind):
        """Coalesce onto the next event-loop turn; a pending rebuild
        subsumes a pending values-only refresh."""
        if self._pending == "rebuild":
            return
        if kind == "rebuild" or self._pending is None:
            already_scheduled = self._pending is not None
            self._pending = kind
            if not already_scheduled:
                QTimer.singleShot(0, self._run_pending)

    def _run_pending(self):
        pending, self._pending = self._pending, None
        if self._detached:
            return
        if pending == "rebuild":
            self._rebuild()
        elif pending == "values":
            self._refresh_values()

    def _rebuild(self):
        self._rebuilding = True
        session = self._model.session
        rois = list(session.rois)
        self.setRowCount(len(rois))
        current = self._model.current_image_path
        stat_cache = {}
        area_per_pixel = self._area_per_pixel()
        # Rebuilt here, not in __init__: the area header names the unit
        # the session is calibrated in, which can change under us.
        self.setHorizontalHeaderLabels(
            [
                f"Area ({self._area_unit()})" if header == "area" else header
                for header in _HEADERS
            ]
        )
        for row, roi in enumerate(rois):
            name_item = QTableWidgetItem(roi.name)
            name_item.setData(Qt.ItemDataRole.UserRole, roi.roi_id)
            self.setItem(row, 0, name_item)
            self.setItem(row, _VISIBLE_COLUMN, self._visible_item(roi))
            self.setItem(row, _BACKGROUND_REF_COLUMN, self._background_ref_item(roi))
            self.setCellWidget(row, 3, self._alpha_spin(roi))
            self.setCellWidget(row, 4, self._color_button(roi))
            self.setCellWidget(
                row,
                5,
                self._combo(
                    _LINE_CHOICES,
                    roi.style.line_style,
                    lambda value, roi=roi: roi.style.trait_set(line_style=value),
                ),
            )
            self.setCellWidget(
                row,
                6,
                self._combo(
                    _MARKER_CHOICES,
                    roi.style.marker,
                    lambda value, roi=roi: roi.style.trait_set(marker=value),
                ),
            )
            self.setCellWidget(row, 7, self._size_spin(roi))
            stats = (
                session.stats.get(session.cache_key(current, roi, stat_cache))
                if current
                else None
            )
            for column, stat in enumerate(
                _STAT_COLUMNS, start=len(_HEADERS) - len(_STAT_COLUMNS)
            ):
                value = stat_value(stats, stat, area_per_pixel)
                text = self._cell_text(stat, value)
                value_item = QTableWidgetItem(text)
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row, column, value_item)
        self._rebuilding = False

    def _cell_text(self, stat, value):
        """Area spans decades with the unit chosen (0.28 mm² is 2.8e+05
        µm²), so it takes a significant-figure format where the
        intensity columns keep their fixed decimal."""
        if value != value:
            return ""
        return f"{value:.4g}" if stat == "area" else f"{value:.1f}"

    def _area_per_pixel(self):
        """One pixel's area in the session's unit (1.0 = px²)."""
        scale = self._model.session.scale
        return pixel_area(scale.metres_per_pixel, scale.unit)

    def _area_unit(self):
        scale = self._model.session.scale
        return area_unit(scale.metres_per_pixel, scale.unit)

    def _refresh_values(self):
        """Rewrite the read-only stat cells in place — no editors or
        row identities touched, so this never deletes a widget the user
        is mid-interaction with."""
        self._rebuilding = True
        session = self._model.session
        rois = list(session.rois)
        current = self._model.current_image_path
        stat_cache = {}
        area_per_pixel = self._area_per_pixel()
        for row, roi in enumerate(rois):
            if row >= self.rowCount():
                break
            stats = (
                session.stats.get(session.cache_key(current, roi, stat_cache))
                if current
                else None
            )
            for column, stat in enumerate(
                _STAT_COLUMNS, start=len(_HEADERS) - len(_STAT_COLUMNS)
            ):
                value = stat_value(stats, stat, area_per_pixel)
                text = self._cell_text(stat, value)
                item = self.item(row, column)
                if item is not None:
                    item.setText(text)
        self._rebuilding = False

    def _on_item_changed(self, item):
        if self._rebuilding:
            return
        if item.column() == _BACKGROUND_REF_COLUMN:
            roi = self._model.session.roi_by_id(item.data(Qt.ItemDataRole.UserRole))
            if roi is not None:
                roi.is_background_ref = item.checkState() == Qt.CheckState.Checked
            return
        if item.column() != 0:
            return
        roi = self._model.session.roi_by_id(item.data(Qt.ItemDataRole.UserRole))
        if roi is not None and item.text().strip():
            roi.name = item.text().strip()

    def _visible_item(self, roi):
        """Eye toggle over roi.style.visible — the plot skips a hidden
        ROI entirely, while its stats and CSV columns stay.

        A cell of glyph text rather than a button inside the cell, the
        way the device viewer's own visibility column works: the font
        rides on the item, so the row reads as one thing instead of
        carrying a widget that draws its own background and border."""
        item = QTableWidgetItem(_visibility_glyph(roi.style.visible))
        item.setFont(QFont(ICON_FONT_FAMILY, EYE_GLYPH_POINT_SIZE))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # Clickable and selectable, but never editable: the click is
        # the control, and a double-click must not open an editor over
        # the glyph.
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setData(Qt.ItemDataRole.UserRole, roi.roi_id)
        item.setToolTip("Show or hide this ROI on the plot")
        return item

    def _background_ref_item(self, roi):
        """Tick to make this ROI a background reference: the marked
        ROIs' mean is what the correction subtracts."""
        item = QTableWidgetItem()
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(
            Qt.CheckState.Checked if roi.is_background_ref else Qt.CheckState.Unchecked
        )
        item.setData(Qt.ItemDataRole.UserRole, roi.roi_id)
        item.setToolTip(
            "Use this ROI as a background reference — the "
            "plot can subtract the marked ROIs' mean"
        )
        return item

    def _on_cell_clicked(self, row, column):
        """The eye cell toggles what it shows — it IS the control."""
        if self._rebuilding or column != _VISIBLE_COLUMN:
            return
        item = self.item(row, column)
        roi = (
            self._model.session.roi_by_id(item.data(Qt.ItemDataRole.UserRole))
            if item
            else None
        )
        if roi is None:
            return
        roi.style.visible = not roi.style.visible
        item.setText(_visibility_glyph(roi.style.visible))

    def _alpha_spin(self, roi):
        spin = QSpinBox(self)
        spin.setRange(*ROI_ALPHA_BOUNDS_PCT)
        spin.setSuffix("%")
        spin.setValue(roi.style.alpha)
        spin.setToolTip("Opacity of this ROI's line on the plot")
        spin.valueChanged.connect(
            lambda value, roi=roi: roi.style.trait_set(alpha=value)
        )
        return spin

    def _color_button(self, roi):
        button = QPushButton(self)
        button.setStyleSheet(f"background-color: {roi.style.color};")
        button.clicked.connect(
            lambda _=False, roi=roi, button=button: self._pick_color(roi, button)
        )
        return button

    def _pick_color(self, roi, button):
        color = QColorDialog.getColor(QColor(roi.style.color), self)
        if color.isValid():
            roi.style.color = color.name()
            button.setStyleSheet(f"background-color: {color.name()};")

    def _combo(self, choices, current, setter):
        combo = QComboBox(self)
        combo.addItems(choices)
        combo.setCurrentText(current)
        combo.currentTextChanged.connect(setter)
        return combo

    def _size_spin(self, roi):
        spin = QDoubleSpinBox(self)
        spin.setRange(*MARKER_SIZE_BOUNDS_PT)
        spin.setValue(roi.style.marker_size)
        spin.valueChanged.connect(
            lambda value, roi=roi: roi.style.trait_set(marker_size=value)
        )
        return spin
