# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Per-ROI tree under the intensity plot, a section per plotted
experiment, in the set's order. A row per ROI, the same in every
section: the eye, the background-reference tick and the style editors
(alpha, color, line, marker, size), then live stats for the image
currently shown in the viewer — including the instant result right
after drawing an ROI.

Only the live experiment — the one the image viewer shows — is edited
here: its ROI names (they drive the plot legend and CSV columns), eyes,
ticks and styles, saved with it. Its section header holds its label,
the prefix its curves carry once it is no longer live. Every other
section shows its experiment as saved: its editors disabled, its value
cells blank, its header row its label, what was found, its
align-to-run-start switch and its remove button. Clicking that row
shows the experiment in the image viewer, which makes it live.

A pure observer of the shared analysis and plotted-experiments models,
mutating them only from Qt editor signals (GUI thread). Rebuilds (rows,
editors, cell identities) on structure/style change; value-refreshes
(stat cells rewritten in place) on stats/current-image change — both
scheduled onto the next event-loop turn so nothing mutates the tree
from inside the emitting Qt signal or traits notification."""

# Enthought library imports.
from pyface.qt.QtCore import QItemSelectionModel, Qt, QTimer
from pyface.qt.QtGui import QColor, QFont, QMouseEvent, QPalette
from pyface.qt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from traitsui.api import HGroup, UItem, View, spring

# Microdrop style imports.
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.icons.icons import (
    ICON_DELETE,
    ICON_VISIBILITY,
    ICON_VISIBILITY_OFF,
)

# Local imports.
from ..scale_bar import area_unit, pixel_area
from .consts import (
    NEGATIVE_MASK_COLOR,
    ROI_ALPHA_BOUNDS_PCT,
    ROI_LINE_WIDTH_BOUNDS_PT,
    SHAPE_STATS,
)
from .plot_series import analysed_paths, shape_reference, stat_value
from .shape_descriptors import shape_deviation


def _visibility_glyph(visible):
    return ICON_VISIBILITY if visible else ICON_VISIBILITY_OFF


#: Value columns after the editors, shown for the current image.
_STAT_COLUMNS = (
    "mean",
    "bg_corrected",
    "median",
    "min",
    "max",
    "count",
    "area",
) + SHAPE_STATS
#: The eye column's header stays blank, as in the device viewer's
#: alpha sidebar; Name keeps column 0, where the rename handler
#: expects it.
_VISIBLE_COLUMN = 1

#: Ticking this marks the ROI as a background reference — a region
#: holding no signal, whose mean the plot can subtract from every
#: ROI.
_BACKGROUND_REF_COLUMN = 2

#: Point size of the eye glyph, matching the device viewer's own
#: visibility column — and of a section's remove glyph.
EYE_GLYPH_POINT_SIZE = 15

#: Marker-size spinner's reach (pt): 1 is barely visible, 30
#: swallows the curve it marks.
MARKER_SIZE_BOUNDS_PT = (1.0, 30.0)

#: The style editors after the background-reference tick, grouped:
#: the colour, the line's look, then the markers'; then the delete
#: cell, its header blank like the eye's.
_HEADERS = (
    "Name",
    "",
    "Bkg Ref",
    "Color",
    "Line",
    "Line width",
    "Line α",
    "Marker",
    "Marker size",
    "Marker α",
    "",
) + _STAT_COLUMNS

#: The first value column, past the editors.
_FIRST_STAT_COLUMN = len(_HEADERS) - len(_STAT_COLUMNS)

#: The delete cell closes the editors: at the far end of the row's
#: controls, clear of the eye and the editors used every day — and a
#: click on it only asks.
_DELETE_COLUMN = _FIRST_STAT_COLUMN - 1

#: The RoiStyle trait each style editor sets, in column order from the
#: one after the background-reference tick.
_STYLE_EDITOR_TRAITS = (
    "color",
    "line_style",
    "line_width",
    "line_alpha",
    "marker",
    "marker_size",
    "alpha",
)

#: The cells whose click is a control acting on every selected row —
#: the click must leave the selection as it is.
_SELECTION_ACTION_COLUMNS = (_VISIBLE_COLUMN, _DELETE_COLUMN)

#: Every cell of a negative mask's row but the eye says what it is.
_NEGATIVE_MASK_TOOLTIP = (
    "Negative mask: subtracted from the ROIs it overlaps while shown; hide "
    "it with the eye to see the numbers without it"
)
#: A mask's name cell on an image captured before the one it was drawn
#: on, where it is neither drawn nor subtracted (Roi.applies_at).
_MASK_NOT_IN_FORCE_TOOLTIP = (
    "Not in force on this image: a mask starts at the image it was drawn on"
)

#: Every editor of an experiment that is not live: it is edited once
#: its section is clicked.
_NOT_LIVE_TOOLTIP = "Select this experiment to edit"

#: Why the value cells of an experiment that is not live are blank.
_NOT_LIVE_VALUE_TOOLTIP = (
    "The values follow the image shown in the viewer: select this "
    "experiment to see its own"
)

_LINE_CHOICES = ("solid", "dashed", "dotted", "dashdot")
_MARKER_CHOICES = ("none", ".", "o", "s", "^", "x")

#: Row count/editors/cell identities change — triggers a full rebuild.
_TABLE_STRUCTURE = (
    "session, session:rois.items, "
    "session:rois:items:name, "
    "session:rois:items:is_negative, "
    "session:rois:items:is_background_ref, "
    "session:rois:items:style:color, "
    "session:scale:metres_per_pixel, "
    "session:scale:unit"
)
#: Only the stat-cell text can be stale — triggers a values-only
#: refresh. The two geometry clauses close a staleness edge: editing an
#: ROI back to an already-cached geometry never bumps stats_revision.
_TABLE_VALUES = (
    "session:stats_revision, current_image_path, filtered_paths.items, "
    "session:rois:items:geometry, "
    "session:rois:items:overrides.items, "
    "session:rois:items:local_overrides, "
    "session:rois:items:absent_at, "
    "session:rois:items:absent_from, "
    "session:rois:items:absent_until"
)
#: The sections change (on the plotted-experiments model), or the ROIs
#: of one — a full rebuild too.
_SECTIONS_STRUCTURE = "experiments.items, experiments:items:session:rois.items"

#: Whether a section's ROIs are shown — its section eye's glyph.
_SECTION_EYES = "experiments:items:any_roi_shown"

#: The ROI tree's own actions: plot another experiment, plot the live
#: one alone again, and copy every plotted curve. A declarative View
#: over an ImportedExperimentsModel, instantiable on its own with
#: ``model.edit_traits(view=imports_toolbar_view)``.
imports_toolbar_view = View(
    HGroup(
        UItem(
            "import_experiment_button",
            tooltip=(
                "Plot another experiment's ROIs beside this one's; click its "
                "section to show it in the image viewer and edit it"
            ),
        ),
        UItem(
            "current_experiment_button",
            tooltip="Plot the experiment the image viewer shows alone again",
        ),
        spring,
        UItem(
            "copy_series_button",
            tooltip=(
                "Copy every plotted curve, every experiment's, as "
                "tab-separated x and value columns"
            ),
        ),
    ),
)


def _listed_rois(session):
    """The live section's row order: the measured ROIs, then the masks
    cut out of them. Rows map back to ROIs by the key their name cells
    carry."""
    return session.positive_rois + session.negative_rois


def _bold(font):
    """``font``, bold."""
    font.setBold(True)

    return font


class RoiStatsTable(QTreeWidget):
    """A section per plotted experiment: the live one's ROIs, then its
    masks, editable; every other one's ROIs as saved. Editors write
    straight into the live ROIs."""

    def __init__(self, model, imports, parent=None):
        super().__init__(parent)
        self._model = model
        self._imports = imports
        self._rebuilding = False
        self._detached = False
        self._pending = None  # None | "rebuild" | "values"

        #: (item, roi) per row of the live experiment's section — the
        #: rows the values-only refresh rewrites.
        self._current_rows = []

        #: The sections the user collapsed, by folder, kept collapsed
        #: across rebuilds.
        self._collapsed = set()

        #: Each section's eye button, by folder, for its glyph to follow
        #: the section's ROIs' eyes; refilled on every rebuild.
        self._section_eyes = {}

        self.setColumnCount(len(_HEADERS))
        self.header().setStretchLastSection(False)

        # Spreadsheet-style: Ctrl/Shift pick ROI and mask rows across
        # sections (a section row is not selectable), and an edit on a
        # selected row applies to every selected one (_targets).
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # An item's flags cover all its columns, so the name alone is
        # opened for editing, by hand, on a double-click.
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.itemChanged.connect(self._on_item_changed)

        # Every committed edit, changed or not: itemChanged stays quiet
        # when the text is unchanged, and re-committing a name another
        # ROI carries must still merge the two.
        self.itemDelegate().commitData.connect(self._on_editor_committed)
        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.itemExpanded.connect(lambda item: self._remember_section(item, True))
        self.itemCollapsed.connect(lambda item: self._remember_section(item, False))

        model.observe(self._on_structure_changed, _TABLE_STRUCTURE)
        model.observe(self._on_values_changed, _TABLE_VALUES)
        imports.observe(self._on_structure_changed, _SECTIONS_STRUCTURE)
        imports.observe(self._on_section_shown_changed, _SECTION_EYES)
        self._rebuild()

    def detach(self):
        # An in-flight coalescing singleShot may fire after the widget's
        # C++ side is gone; the flag makes it a no-op.
        self._detached = True
        self._model.observe(self._on_structure_changed, _TABLE_STRUCTURE, remove=True)
        self._model.observe(self._on_values_changed, _TABLE_VALUES, remove=True)
        self._imports.observe(
            self._on_structure_changed, _SECTIONS_STRUCTURE, remove=True
        )
        self._imports.observe(
            self._on_section_shown_changed, _SECTION_EYES, remove=True
        )

    def selectionCommand(self, index, event=None):
        """A plain click on a selected row's eye or delete cell keeps the
        selection: the click acts on every selected row, and Qt would
        otherwise narrow the selection to the clicked row on release,
        before itemClicked. The editor widgets need no such care: a
        click on one never reaches the tree."""
        if (
            isinstance(event, QMouseEvent)
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and index.column() in _SELECTION_ACTION_COLUMNS
            and self.selectionModel().isSelected(index)
        ):
            return QItemSelectionModel.SelectionFlag.NoUpdate

        return super().selectionCommand(index, event)

    def _on_structure_changed(self, event):
        self._schedule("rebuild")

    def _on_section_shown_changed(self, event):
        """A section's ROIs were shown or hidden: its eye follows."""
        eye = self._section_eyes.get(event.object.directory)

        if eye is not None:
            eye.setText(_visibility_glyph(event.object.any_roi_shown))

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
        experiments = self._imports.experiments

        # Kept across the rebuild: a bulk colour change, say, rebuilds
        # with the same rows selected and in view.
        selected = set(self._selected_keys())
        scrolled = self.verticalScrollBar().value()

        # The items take their editor widgets with them.
        self.clear()
        self._current_rows = []
        self._section_eyes = {}

        # Rebuilt here, not in __init__: the area header names the unit
        # the session is calibrated in, which can change under us.
        self.setHeaderLabels(
            [
                f"Area ({self._area_unit()})" if header == "area" else header
                for header in _HEADERS
            ]
        )

        # With no experiment shown there is none live, but the session's
        # ROIs are still listed, first.
        if not any(experiment.live for experiment in experiments):
            self._add_live_section(None)

        for experiment in experiments:
            if experiment.live:
                self._add_live_section(experiment)
            else:
                self._add_stored_section(experiment)

        # Once filled: a section is expanded with its rows in place.
        for index in range(self.topLevelItemCount()):
            section = self.topLevelItem(index)
            key = section.data(0, Qt.ItemDataRole.UserRole)
            section.setExpanded(key not in self._collapsed)

        for item in self._items_of(selected):
            item.setSelected(True)

        self.verticalScrollBar().setValue(scrolled)
        self._rebuilding = False

    def _selected_keys(self):
        """The keys of the selected ROI and mask rows."""
        return [
            item.data(0, Qt.ItemDataRole.UserRole)
            for item in self.selectedItems()
            if item.parent() is not None
        ]

    def _targets(self, key):
        """What an edit on the row ``key`` acts on: every selected row's
        key while that row is one of them, else that row's alone."""
        selected = self._selected_keys()

        return selected if key in selected else [key]

    def _items_of(self, keys):
        """The ROI and mask rows whose keys are among ``keys``."""
        items = []

        for index in range(self.topLevelItemCount()):
            section = self.topLevelItem(index)

            for row in range(section.childCount()):
                item = section.child(row)

                if item.data(0, Qt.ItemDataRole.UserRole) in keys:
                    items.append(item)

        return items

    def _section_item(self, key):
        """A top-level section row across every column, keyed by its
        experiment's folder, ``key``."""
        section = QTreeWidgetItem(self)
        section.setData(0, Qt.ItemDataRole.UserRole, key)
        section.setFlags(Qt.ItemFlag.ItemIsEnabled)
        section.setFirstColumnSpanned(True)

        return section

    def _add_live_section(self, experiment):
        """The section of the live ``experiment`` — None for the session
        of no experiment: its header, then its ROIs and masks with every
        editor and the shown image's values."""
        session = self._model.session
        current = self._model.current_image_path
        paths = analysed_paths(session, self._model.filtered_paths)
        stat_cache = {}
        area_per_pixel = self._area_per_pixel()

        if experiment is None:
            section = self._section_item("")
            section.setText(0, "This experiment")
            section.setFont(0, _bold(section.font(0)))
        else:
            section = self._section_item(experiment.directory)
            self.setItemWidget(section, 0, self._live_header(experiment))

        for roi in _listed_rois(session):
            item = self._roi_item(section, roi, roi.roi_id, live=True)
            self._current_rows.append((item, roi))

            if roi.is_negative:
                self._fill_mask_row(item, roi, current, stat_cache)
                continue

            self._fill_style_cells(item, roi, live=True)
            texts = self._stat_texts(roi, current, paths, stat_cache, area_per_pixel)

            for column, text in enumerate(texts, start=_FIRST_STAT_COLUMN):
                item.setText(column, text)

    def _add_stored_section(self, experiment):
        """The section of ``experiment``, not live, as saved: its
        header, then a row per ROI with its editors disabled and its
        value cells blank — they would follow the image shown, which is
        never one of its own."""
        section = self._section_item(experiment.directory)
        self.setItemWidget(section, 0, self._stored_header(experiment))

        for roi in experiment.session.positive_rois:
            item = self._roi_item(section, roi, experiment.key_of(roi), live=False)
            self._fill_style_cells(item, roi, live=False)

            for column in range(_FIRST_STAT_COLUMN, len(_HEADERS)):
                item.setToolTip(column, _NOT_LIVE_VALUE_TOOLTIP)

    def _live_header(self, experiment):
        """The live experiment's section row: its eye, its label, edited
        to name its curves once another experiment is live, and the live
        mark."""
        header = QWidget(self)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_eye(experiment, header))

        label = QLineEdit(experiment.label, header)
        label.setFrame(False)
        label.setFont(_bold(label.font()))
        label.setToolTip(
            "This experiment's name in the legend and the copied data while "
            "another experiment is live"
        )
        label.editingFinished.connect(
            lambda: experiment.trait_set(label=label.text().strip() or experiment.label)
        )
        layout.addWidget(label, 1)

        live = QLabel("(live)", header)
        live.setFont(_bold(live.font()))
        live.setToolTip("The experiment the image viewer shows, edited here")
        layout.addWidget(live)

        return header

    def _stored_header(self, experiment):
        """The section row of ``experiment``, not live: its eye, its
        label, what was found, its align-to-run-start switch and its
        remove button.
        A click anywhere else on it falls through to the tree, which
        shows the experiment in the image viewer (_on_item_clicked)."""
        header = QWidget(self)
        header.setToolTip(
            "Click to show this experiment in the image viewer and edit it"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_eye(experiment, header))

        label = QLabel(experiment.label, header)
        label.setFont(_bold(label.font()))
        layout.addWidget(label)

        found = QLabel(experiment.summary, header)
        found.setEnabled(False)  # greyed: a note, not a control
        layout.addWidget(found)
        layout.addStretch(1)

        align = QCheckBox("Align to run start", header)
        align.setChecked(experiment.align_to_run_start)
        align.setToolTip(
            "On the time axis, plot this run from its own first capture; "
            "off, on the live experiment's clock as captured"
        )
        align.toggled.connect(
            lambda checked: experiment.trait_set(align_to_run_start=checked)
        )
        layout.addWidget(align)

        remove = QToolButton(header)
        remove.setText(ICON_DELETE)
        remove.setFont(QFont(ICON_FONT_FAMILY, EYE_GLYPH_POINT_SIZE))
        remove.setAutoRaise(True)
        remove.setToolTip(
            "Stop plotting this experiment: its ROIs leave the table and the plot"
        )
        remove.clicked.connect(lambda: experiment.trait_set(remove=True))
        layout.addWidget(remove)

        return header

    def _section_eye(self, experiment, header):
        """The eye on ``experiment``'s section row: shows "visible" while
        any of its ROIs is shown, and a click hides them all — or, all
        hidden, shows them all. A button, so its click is its own and
        never falls through to the section's navigation."""
        eye = QToolButton(header)
        eye.setText(_visibility_glyph(experiment.any_roi_shown))
        eye.setFont(QFont(ICON_FONT_FAMILY, EYE_GLYPH_POINT_SIZE))
        eye.setAutoRaise(True)
        eye.setToolTip(
            "Show or hide every ROI of this experiment on the plot (masks "
            "keep their own eyes)"
        )
        eye.clicked.connect(lambda: self._toggle_section_shown(experiment))
        self._section_eyes[experiment.directory] = eye

        return eye

    def _toggle_section_shown(self, experiment):
        """Show or hide ``experiment``'s ROIs at once, then redraw the
        rows, whose eyes all changed."""
        experiment.toggle_rois_shown()
        self._schedule("rebuild")

    def _roi_item(self, section, roi, key, live):
        """``roi``'s row in ``section``, its name cell carrying the
        ``key`` its curve has, with its eye. A ``live`` experiment's row
        can be renamed and its background reference ticked."""
        item = QTreeWidgetItem(section, [roi.name])
        item.setData(0, Qt.ItemDataRole.UserRole, key)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        if live:
            flags |= Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable

        item.setFlags(flags)
        self._fill_visible_cell(item, roi, live)
        self._fill_delete_cell(item, roi)

        return item

    def _fill_delete_cell(self, item, roi):
        """The delete glyph — a cell of glyph text, as the eye's — whose
        click asks to delete ``roi`` from every image (_on_item_clicked)."""
        kind = "mask" if roi.is_negative else "ROI"

        item.setText(_DELETE_COLUMN, ICON_DELETE)
        item.setFont(_DELETE_COLUMN, QFont(ICON_FONT_FAMILY, EYE_GLYPH_POINT_SIZE))
        item.setTextAlignment(_DELETE_COLUMN, Qt.AlignmentFlag.AlignCenter)
        item.setToolTip(_DELETE_COLUMN, f"Delete this {kind} from every image")

    def _fill_visible_cell(self, item, roi, live):
        """Eye toggle over roi.style.visible — the plot skips a hidden
        ROI entirely, while its stats and CSV columns stay; a hidden
        mask is left out of the calculation.

        A cell of glyph text rather than a button inside the cell, the
        way the device viewer's own visibility column works: the font
        rides on the item, so the row reads as one thing instead of
        carrying a widget that draws its own background and border.
        The click is the control (see _on_item_clicked), and with no
        edit triggers a double-click opens no editor over the glyph."""
        item.setText(_VISIBLE_COLUMN, _visibility_glyph(roi.style.visible))
        item.setFont(_VISIBLE_COLUMN, QFont(ICON_FONT_FAMILY, EYE_GLYPH_POINT_SIZE))
        item.setTextAlignment(_VISIBLE_COLUMN, Qt.AlignmentFlag.AlignCenter)

        if roi.is_negative:
            tooltip = (
                "Show or hide this mask on the image — a hidden mask is not subtracted"
            )
        else:
            tooltip = (
                "Show or hide this ROI on the plot and the image (it is still "
                "measured and exported)"
            )

        item.setToolTip(_VISIBLE_COLUMN, tooltip)

    def _fill_style_cells(self, item, roi, live):
        """A measured ROI's background-reference tick — ticked, the
        marked ROIs' mean is what the correction subtracts, editable
        only while ``live`` — and its style editors, editable in every
        section."""
        item.setCheckState(
            _BACKGROUND_REF_COLUMN,
            Qt.CheckState.Checked if roi.is_background_ref else Qt.CheckState.Unchecked,
        )
        item.setToolTip(
            _BACKGROUND_REF_COLUMN,
            (
                "Use this ROI as a background reference — the plot can "
                "subtract the marked ROIs' mean"
            )
            if live
            else _NOT_LIVE_TOOLTIP,
        )
        key = item.data(0, Qt.ItemDataRole.UserRole)
        editors = [
            self._color_button(key, roi),
            self._combo(key, roi, "line_style", _LINE_CHOICES),
            self._size_spin(
                key,
                roi,
                "line_width",
                ROI_LINE_WIDTH_BOUNDS_PT,
                "Width of this ROI's curve and its fits on the plot (pt)",
            ),
            self._alpha_spin(
                key,
                roi,
                "line_alpha",
                "Opacity of this ROI's curve, its fits and their equations",
            ),
            self._combo(key, roi, "marker", _MARKER_CHOICES),
            self._size_spin(
                key,
                roi,
                "marker_size",
                MARKER_SIZE_BOUNDS_PT,
                "Size of this ROI's markers on the plot (pt)",
            ),
            self._alpha_spin(
                key,
                roi,
                "alpha",
                "Opacity of this ROI's points: its markers, excluded points, "
                "fit landmarks, bars, violins and histogram fills",
            ),
        ]

        for column, editor in enumerate(editors, start=_BACKGROUND_REF_COLUMN + 1):
            self.setItemWidget(item, column, editor)

    def _apply_style(self, key, **traits):
        """An editor on the row ``key`` changed: set ``traits`` on the
        style of every row it acts on (_targets) — masks only their eye —
        then show the new values in the other rows' editors."""
        keys = self._targets(key)
        self._imports.restyle_rois(keys, **traits)

        if len(keys) > 1:
            self._show_styles(keys)

    def _show_styles(self, keys):
        """Rewrite the editors and eyes of the rows ``keys`` from their
        ROIs' styles, in place — signals blocked, so showing a value
        never sets it again; a mask row has its eye alone."""
        for item in self._items_of(keys):
            roi = self._roi_of(item.data(0, Qt.ItemDataRole.UserRole))

            if roi is None:
                continue

            item.setText(_VISIBLE_COLUMN, _visibility_glyph(roi.style.visible))

            for column, name in enumerate(
                _STYLE_EDITOR_TRAITS, start=_BACKGROUND_REF_COLUMN + 1
            ):
                editor = self.itemWidget(item, column)

                if editor is None:
                    continue

                value = getattr(roi.style, name)
                editor.blockSignals(True)

                if isinstance(editor, QPushButton):
                    editor.setStyleSheet(f"background-color: {value};")
                elif isinstance(editor, QComboBox):
                    editor.setCurrentText(value)
                else:
                    editor.setValue(value)

                editor.blockSignals(False)

    def _roi_of(self, key):
        """The ROI, live or not, the row ``key`` names; None for none."""
        roi = self._model.session.roi_by_id(key)

        return self._imports.roi_of(key) if roi is None else roi

    def _fill_mask_row(self, item, roi, current, stat_cache):
        """A mask has no stats, no plot style and is never a background
        reference: past its name and eye, every cell is a blank saying
        what it is."""
        self._mark_mask_in_force(item, roi, current, stat_cache)

        for column in range(_BACKGROUND_REF_COLUMN, len(_HEADERS)):
            if column != _DELETE_COLUMN:
                item.setToolTip(column, _NEGATIVE_MASK_TOOLTIP)

    def _mark_mask_in_force(self, item, roi, current, stat_cache):
        """Name a mask in its own colour where it is in force on the
        ``current`` image, and in the palette's disabled grey, with a
        tooltip saying why, on an image before the one it was drawn on.
        With no image shown every mask counts as in force."""
        in_force = not current or roi.applies_at(
            self._model.session.stat_info(current, stat_cache)[1]
        )

        if in_force:
            item.setForeground(0, QColor(NEGATIVE_MASK_COLOR))
            item.setToolTip(0, _NEGATIVE_MASK_TOOLTIP)
        else:
            item.setForeground(
                0,
                self.palette().color(
                    QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
                ),
            )
            item.setToolTip(0, _MASK_NOT_IN_FORCE_TOOLTIP)

    def _stat_texts(self, roi, current, paths, stat_cache, area_per_pixel):
        """The ``_STAT_COLUMNS`` cell texts of ``roi`` on the ``current``
        image. Shape change is measured from the ROI's first analysed
        image (of ``paths``) with a droplet — the plot's own reference."""
        session = self._model.session
        stats = (
            session.stats.get(session.cache_key(current, roi, stat_cache))
            if current
            else None
        )
        reference = shape_reference(
            [
                session.stats.get(session.cache_key(path, roi, stat_cache))
                for path in paths
            ]
        )
        texts = []

        for stat in _STAT_COLUMNS:
            if stat == "shape_change":
                value = shape_deviation(stats or {}, reference or {})
            else:
                value = stat_value(stats, stat, area_per_pixel)

            texts.append(self._cell_text(stat, value))

        return texts

    def _cell_text(self, stat, value):
        """Area spans decades with the unit chosen (0.28 mm² is 2.8e+05
        µm²), so it takes a significant-figure format where the
        intensity columns keep their fixed decimal; the unitless shape
        quantities live near 1 (or 0), so they keep three. The
        orientation is in degrees, where one decimal is already finer
        than its noise."""
        if value != value:
            return ""

        if stat == "area":
            return f"{value:.4g}"

        if stat in SHAPE_STATS and stat != "orientation_deg":
            return f"{value:.3f}"

        return f"{value:.1f}"

    def _area_per_pixel(self):
        """One pixel's area in the session's unit (1.0 = px²)."""
        scale = self._model.session.scale

        return pixel_area(scale.metres_per_pixel, scale.unit)

    def _area_unit(self):
        scale = self._model.session.scale

        return area_unit(scale.metres_per_pixel, scale.unit)

    def _refresh_values(self):
        """Rewrite the current section's read-only stat cells, and
        whether each mask is in force on the current image, in place —
        no editors or row identities touched, so this never deletes a
        widget the user is mid-interaction with."""
        self._rebuilding = True
        session = self._model.session
        current = self._model.current_image_path
        paths = analysed_paths(session, self._model.filtered_paths)
        stat_cache = {}
        area_per_pixel = self._area_per_pixel()

        for item, roi in self._current_rows:
            if roi.is_negative:
                self._mark_mask_in_force(item, roi, current, stat_cache)
                continue

            texts = self._stat_texts(roi, current, paths, stat_cache, area_per_pixel)

            for column, text in enumerate(texts, start=_FIRST_STAT_COLUMN):
                item.setText(column, text)

        self._rebuilding = False

    def _on_item_changed(self, item, column):
        """The Bkg Ref tick changed (names go through _on_editor_committed);
        only a live ROI's can be."""
        if self._rebuilding or column != _BACKGROUND_REF_COLUMN:
            return

        roi = self._model.session.roi_by_id(item.data(0, Qt.ItemDataRole.UserRole))

        if roi is not None:
            roi.is_background_ref = item.checkState(column) == Qt.CheckState.Checked

    def _on_editor_committed(self, editor):
        """A name edit was committed: ask for the rename
        (RoiAnalysisController decides whether it is a merge). Only a
        live ROI's name opens an editor."""
        # The cell being edited is the current one.
        item = self.currentItem()
        name = editor.text().strip() if hasattr(editor, "text") else ""

        if item is None or self.currentColumn() != 0 or not name:
            return

        request = (item.data(0, Qt.ItemDataRole.UserRole), name)
        model = self._model

        # Out of Qt's own edit: a merge removes this very row.
        QTimer.singleShot(0, lambda: model.trait_set(rename_roi_request=request))

    def _on_item_double_clicked(self, item, column):
        """Open a live ROI's name for editing."""
        if column == 0 and item.flags() & Qt.ItemFlag.ItemIsEditable:
            self.editItem(item, 0)

    def _on_item_clicked(self, item, column):
        """A section click shows its experiment in the image viewer,
        unless it is live already. An ROI's eye cell toggles what it
        shows — it IS the control — and its delete cell asks to delete
        it; on a selected row, each acts on every selected row, the
        eyes all set to the clicked row's new state."""
        if self._rebuilding:
            return

        key = item.data(0, Qt.ItemDataRole.UserRole)

        if item.parent() is None:
            self._open_experiment(key)

            return

        if column == _DELETE_COLUMN:
            imports = self._imports
            keys = self._targets(key)

            # The confirmation is modal: out of this click's own handler.
            QTimer.singleShot(0, lambda: imports.trait_set(delete_roi_request=keys))

            return

        roi = self._roi_of(key)

        if column != _VISIBLE_COLUMN or roi is None:
            return

        keys = self._targets(key)
        self._imports.restyle_rois(keys, visible=not roi.style.visible)
        self._show_styles(keys)

    def _open_experiment(self, directory):
        """Ask for the plotted experiment in ``directory`` to be shown in
        the image viewer, unless it is live already."""
        stored = any(
            experiment.directory == directory and not experiment.live
            for experiment in self._imports.experiments
        )

        if stored:
            self._imports.open_experiment_request = directory

    def _remember_section(self, item, expanded):
        """Keep a section the user collapsed collapsed across rebuilds."""
        if self._rebuilding:
            return

        key = item.data(0, Qt.ItemDataRole.UserRole)

        if expanded:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)

    def _alpha_spin(self, key, roi, name, tooltip):
        """A percentage spinner over the opacity ``name`` of the style of
        ``roi``, the row ``key``'s."""
        spin = QSpinBox(self)
        spin.setRange(*ROI_ALPHA_BOUNDS_PCT)
        spin.setSuffix("%")
        spin.setValue(getattr(roi.style, name))
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(lambda value: self._apply_style(key, **{name: value}))

        return spin

    def _color_button(self, key, roi):
        button = QPushButton(self)
        button.setStyleSheet(f"background-color: {roi.style.color};")
        button.clicked.connect(lambda: self._pick_color(key, roi, button))

        return button

    def _pick_color(self, key, roi, button):
        """Pick the colour of the row ``key`` — every selected row's,
        it being one of them, as they stood when the picker opened."""
        keys = self._targets(key)
        color = QColorDialog.getColor(QColor(roi.style.color), self)

        if not color.isValid():
            return

        button.setStyleSheet(f"background-color: {color.name()};")
        self._imports.restyle_rois(keys, color=color.name())

        if len(keys) > 1:
            self._show_styles(keys)

    def _combo(self, key, roi, name, choices):
        """A dropdown of ``choices`` over the style trait ``name`` of
        ``roi``, the row ``key``'s."""
        combo = QComboBox(self)
        combo.addItems(choices)
        combo.setCurrentText(getattr(roi.style, name))
        combo.currentTextChanged.connect(
            lambda value: self._apply_style(key, **{name: value})
        )

        return combo

    def _size_spin(self, key, roi, name, bounds, tooltip):
        """A point-size spinner, within ``bounds``, over the size
        ``name`` of the style of ``roi``, the row ``key``'s."""
        spin = QDoubleSpinBox(self)
        spin.setRange(*bounds)
        spin.setSingleStep(0.5)
        spin.setValue(getattr(roi.style, name))
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(lambda value: self._apply_style(key, **{name: value}))

        return spin
