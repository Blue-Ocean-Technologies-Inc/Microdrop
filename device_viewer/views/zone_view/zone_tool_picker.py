# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Zone tool grid for the zones sidebar: a Paths-mode-picker-style widget of
checkable Draw/Select tool buttons plus Commit/Clear action buttons, bound to
a ``ZoneLayerManager``. Standalone: ``zone_tool_picker_factory`` is the
``CustomEditor`` factory used by ``zones_sidebar.zones_view``."""

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.qt.QtCore import QEvent, QObject, Signal
from pyface.qt.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE
from device_viewer.models.zones import ZoneLayerManager

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_ADD,
    ICON_CALL_TO_ACTION,
    ICON_CHECK,
    ICON_CROP,
    ICON_DELETE,
    ICON_SELECT_All,
)


class ZoneToolPickerSignals(QObject):
    """Qt signal bridge for ``ZoneToolPickerViewModel``."""

    #: Emitted whenever any state the view renders (active tool, pending
    #: selection, edit-in-progress) changes, requiring a UI refresh.
    state_changed = Signal()


class ZoneToolPickerViewModel(HasTraits):
    """Qt-free logic for the zone tool grid: tool toggling and the
    commit/clear actions, plus the button states the view syncs to."""

    #: Zone state the picker edits.
    manager = Instance(ZoneLayerManager)

    #: Signal bridge to the Qt view.
    signals = Instance(ZoneToolPickerSignals)

    def traits_init(self):
        self.signals = ZoneToolPickerSignals()

    # -- Actions --
    def toggle_tool(self, mode):
        """Activate ``mode``, or turn the zone tools off if it is already
        active (clicking the active tool again)."""
        self.manager.mode = "" if self.manager.mode == mode else mode

    def commit(self):
        self.manager.commit_button = True

    def clear(self):
        self.manager.clear_pending_button = True

    def toggle_overlays(self):
        self.manager.show_canvas_overlays = not self.manager.show_canvas_overlays

    # -- Properties for the view --
    @property
    def draw_active(self):
        return self.manager.mode == ZONE_DRAW_MODE

    @property
    def select_active(self):
        return self.manager.mode == ZONE_SELECT_MODE

    @property
    def commit_enabled(self):
        return (
            self.manager.mode == ZONE_DRAW_MODE
            and len(self.manager.pending_electrode_ids) > 0
        )

    @property
    def clear_enabled(self):
        return (
            len(self.manager.pending_electrode_ids) > 0
            or self.manager.editing_region is not None
        )

    @property
    def overlays_active(self):
        return self.manager.show_canvas_overlays

    @observe(
        "manager:mode, manager:pending_electrode_ids.items, "
        "manager:editing_region, manager:show_canvas_overlays"
    )
    def _on_underlying_state_changed(self, event):
        """Forward underlying model changes to the Qt view."""
        self.signals.state_changed.emit()


def wrap_button_row(widget, row_layout):
    """Mount ``row_layout`` on ``widget`` the way the Paths picker mounts
    its rows. TraitsUI zeroes the margins of the layout it embeds, so the
    row lives in a child widget whose default layout margins match the
    Paths picker's and keep every zone button row aligned with it."""
    row_widget = QWidget(widget)
    row_widget_layout = QVBoxLayout(row_widget)
    row_widget_layout.addLayout(row_layout)

    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(row_widget)


class ZoneToolPicker(QWidget):
    """Draw / Select tool buttons and Commit / Clear action buttons, laid
    out in one row like the Paths ``ModePicker``."""

    def __init__(self, view_model):
        super().__init__()
        self.vm = view_model

        self._init_ui_elements()
        self._layout_ui()
        self._bind_signals()

        self.sync_ui()

    def _init_ui_elements(self):
        self.button_draw = QPushButton(ICON_CROP)
        self.button_draw.setToolTip("Draw zones")
        self.button_draw.setCheckable(True)

        self.button_select = QPushButton(ICON_SELECT_All)
        self.button_select.setToolTip("Select zones")
        self.button_select.setCheckable(True)

        self.button_commit = QPushButton(ICON_CHECK)
        self.button_commit.setToolTip("Commit zone")

        self.button_clear = QPushButton(ICON_DELETE)
        self.button_clear.setToolTip("Clear selection")

    def _layout_ui(self):
        # One flat row, laid out like the Paths picker's rows: natural-size
        # buttons, left aligned, trailing stretch.
        row_layout = QGridLayout()
        row_layout.addWidget(self.button_draw, 0, 0)
        row_layout.addWidget(self.button_select, 0, 1)
        row_layout.addWidget(self.button_commit, 0, 2)
        row_layout.addWidget(self.button_clear, 0, 3)
        row_layout.setColumnStretch(4, 1)

        wrap_button_row(self, row_layout)

    def _bind_signals(self):
        # View -> ViewModel (user actions)
        self.button_draw.clicked.connect(partial(self.vm.toggle_tool, ZONE_DRAW_MODE))
        self.button_select.clicked.connect(
            partial(self.vm.toggle_tool, ZONE_SELECT_MODE)
        )
        self.button_commit.clicked.connect(self.vm.commit)
        self.button_clear.clicked.connect(self.vm.clear)

        # ViewModel -> View (state updates)
        self.vm.signals.state_changed.connect(self.sync_ui)

    def sync_ui(self):
        """Update checked/enabled state from the view model."""
        self.button_draw.setChecked(self.vm.draw_active)
        self.button_select.setChecked(self.vm.select_active)
        self.button_commit.setEnabled(self.vm.commit_enabled)
        self.button_clear.setEnabled(self.vm.clear_enabled)


def zone_tool_picker_factory(parent, editor):
    """TraitsUI ``CustomEditor`` factory: the editor's object is the manager."""
    return ZoneToolPicker(ZoneToolPickerViewModel(manager=editor.object))


class AddZoneTypeButton(QWidget):
    """The zone-types table's add button: one button in a row built like
    the tool row, as wide as the tool row's four buttons merged."""

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.button = QPushButton(ICON_ADD)
        self.button.setToolTip("Add zone type")
        self.button.clicked.connect(self._on_clicked)

        self.row_layout = QGridLayout()
        self.row_layout.addWidget(self.button, 0, 0)
        self.row_layout.setColumnStretch(1, 1)
        wrap_button_row(self, self.row_layout)

    def _on_clicked(self):
        self.manager.add_zone_type_button = True

    def _fit_to_tool_row(self):
        """Every glyph button shares one size hint, so four of them plus
        three gaps is the tool row's width. Re-run whenever the stylesheet
        changes, since it sets the button padding."""
        spacing = self.row_layout.horizontalSpacing()
        if spacing < 0:
            spacing = self.style().pixelMetric(
                QStyle.PixelMetric.PM_LayoutHorizontalSpacing
            )
        self.button.setFixedWidth(4 * self.button.sizeHint().width() + 3 * spacing)

    def showEvent(self, event):
        self._fit_to_tool_row()
        super().showEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.StyleChange:
            self._fit_to_tool_row()
        super().changeEvent(event)


def add_zone_type_button_factory(parent, editor):
    """TraitsUI ``CustomEditor`` factory: the editor's object is the manager."""
    return AddZoneTypeButton(editor.object)


class CanvasOverlaysToggle(QPushButton):
    """Checkable button mirroring ``show_canvas_overlays``: checked (and
    highlighted by the sidebar stylesheet) while the floating canvas
    buttons are shown, like the Draw/Select tool buttons."""

    def __init__(self, view_model):
        super().__init__(ICON_CALL_TO_ACTION)
        self.vm = view_model
        self.setCheckable(True)
        self.setToolTip("Show or hide the floating canvas buttons")
        self.clicked.connect(self.vm.toggle_overlays)
        self.vm.signals.state_changed.connect(self.sync_ui)
        self.sync_ui()

    def sync_ui(self):
        self.setChecked(self.vm.overlays_active)


def canvas_overlays_toggle_factory(parent, editor):
    """TraitsUI ``CustomEditor`` factory: the editor's object is the manager.
    TraitsUI stretches the editor it embeds, so the button sits in a
    container with a trailing stretch and keeps its natural size."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(
        CanvasOverlaysToggle(ZoneToolPickerViewModel(manager=editor.object))
    )
    layout.addStretch(1)
    return container
