# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The protocol pane's widgets in the app status bar: the AutoSave glyph on
the right; on the left, after the pre-flight pill, the step navigator and
the protocol chip.

    [● Ready] ‹ Step 2.1 · 3/8 › ⊘ [▤ mixing-assay] [⬡ Chip-120]

The navigator's ‹ › step through the protocol as the navigation bar does
(idle or paused), ⊘ deselects back to free mode, and while a run is active
it reads "Running · Step 2.1" ("Paused", "Preview"). The chip names the
protocol, washed green saved, amber unsaved, red when the pre-flight check
finds electrodes the loaded device lacks, and opens a menu of the protocol
file actions.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_status_bar.consts import (
    LEFT_PRIORITY_NAVIGATION,
    LEFT_PRIORITY_PRIMARY_FILE,
    STATUS_BAR_GROUP_FILE_CHIPS,
    STATUS_BAR_SIDE_LEFT,
)
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.preflight.consts import CHECK_ELECTRODES_EXIST
from pluggable_protocol_tree.preflight.models import PreflightReport
from pluggable_protocol_tree.services.device_viewer_sync import (
    DeviceViewerSyncController,
    write_back_targets,
)
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)
from pluggable_protocol_tree.views.autosave_status_icon import AutosaveStatusIcon
from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_BLOCK,
    ICON_CHEVRON_LEFT,
    ICON_CHEVRON_RIGHT,
    ICON_DESCRIPTION,
)
from microdrop_style.panel_theme import icon_button_style, theme_palette

# Microdrop utils imports.
from microdrop_utils.status_chip import (
    CHIP_HEIGHT,
    FileChip,
    chip_menu,
    follow_theme,
    open_menu_above,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Glyph size of the navigator's buttons, px.
NAV_GLYPH_PX = 16

#: Space between the navigator's label and its buttons, px.
NAV_SPACING = 2

#: The protocol chip's note for a file never saved.
UNSAVED_PATH_NOTE = "Not saved to a file yet"


class StepNavigator(QtWidgets.QWidget):
    """``‹ Step 2.1 · 3/8 › ⊘``: tight, flat glyph buttons as tall as the
    chips around the step label."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(NAV_SPACING)

        self.previous = QtWidgets.QToolButton(text=ICON_CHEVRON_LEFT)
        self.previous.setToolTip("Previous step")

        self.label = QtWidgets.QLabel()

        self.next = QtWidgets.QToolButton(text=ICON_CHEVRON_RIGHT)
        self.next.setToolTip("Next step")

        self.free_mode = QtWidgets.QToolButton(text=ICON_BLOCK)
        self.free_mode.setToolTip("Deselect: back to free mode")

        for button in self._buttons():
            button.setFixedSize(CHIP_HEIGHT, CHIP_HEIGHT)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self.previous)
        layout.addWidget(self.label)
        layout.addWidget(self.next)
        layout.addSpacing(NAV_SPACING)
        layout.addWidget(self.free_mode)

        self._restyle()
        follow_theme(self._restyle)

    def show_step(self, text, navigable, deselectable, can_previous, can_next):
        """Show ``text``; ‹ › while ``navigable``, enabled by
        ``can_previous`` / ``can_next``; ⊘ while ``deselectable``."""
        self.label.setText(text)

        self.previous.setVisible(navigable)
        self.next.setVisible(navigable)
        self.free_mode.setVisible(deselectable)

        self.previous.setEnabled(can_previous)
        self.next.setEnabled(can_next)

    def _buttons(self):
        return (self.previous, self.next, self.free_mode)

    def _restyle(self, *_):
        style = (
            f"{icon_button_style(theme_palette(), NAV_GLYPH_PX)}"
            " QToolButton { padding: 0px; }"
        )

        for button in self._buttons():
            button.setStyleSheet(style)


class ProtocolStatusBarWidgets(HasTraits):
    """Builds the protocol pane's status-bar widgets, keeps them in step
    with the protocol, its file and its run, and puts them in the bar."""

    #: The protocol dock pane: its step navigation, file actions and run
    #: state.
    dock_pane = Any()

    #: The pane's protocol tree view, with its AutoSave controller.
    tree_pane = Instance(ProtocolTreePane)

    #: What the widgets show, taken from the dock pane: the protocol's rows
    #: and file state, the executor's status, the device-viewer sync, and
    #: the pre-flight report with the preferences that enable it.
    manager = Instance(RowManager)
    tracker = Instance(PluggableProtocolStateTracker)
    status_model = Instance(ProtocolStatusModel)
    sync = Instance(DeviceViewerSyncController)
    report = Instance(PreflightReport)
    preferences = Instance(ProtocolPreferences)

    #: The widgets; None once withdrawn.
    autosave_icon = Instance(AutosaveStatusIcon)
    navigator = Instance(StepNavigator)
    protocol_chip = Instance(FileChip)

    #: The navigable steps, cached until the protocol's structure changes;
    #: None when stale.
    _steps = Any()

    #: The tree's selection model whose ``currentChanged`` drives the
    #: navigator, kept to disconnect from on withdraw.
    _selection_model = Any()

    def traits_init(self):
        pane = self.dock_pane

        self.autosave_icon = AutosaveStatusIcon(
            model=self.tree_pane.autosave_controller.model
        )

        self.navigator = StepNavigator()
        self.navigator.status_bar_side = STATUS_BAR_SIDE_LEFT
        self.navigator.status_bar_left_priority = LEFT_PRIORITY_NAVIGATION
        self.navigator.previous.clicked.connect(pane.navigate_to_previous_step)
        self.navigator.next.clicked.connect(pane.navigate_to_next_step)
        self.navigator.free_mode.clicked.connect(self._tree().clear_to_free_mode)

        self.protocol_chip = FileChip(ICON_DESCRIPTION, "protocolChip")
        self.protocol_chip.status_bar_side = STATUS_BAR_SIDE_LEFT
        self.protocol_chip.status_bar_left_priority = LEFT_PRIORITY_PRIMARY_FILE
        self.protocol_chip.status_bar_group = STATUS_BAR_GROUP_FILE_CHIPS
        self.protocol_chip.clicked.connect(self._open_protocol_menu)

        # The tree's current row is the step shown while no run is active.
        self._selection_model = self._tree().selectionModel()
        self._selection_model.currentChanged.connect(self._on_current_changed)

        self.trait_set(
            manager=pane.manager,
            tracker=pane.protocol_state_tracker,
            status_model=pane.status_controller.model,
            sync=pane.sync,
            report=pane.preflight.controller.report,
            preferences=pane.preferences,
        )

        self.show_step()
        self.show_protocol()

    # ------------------------------------------------------------------
    # The status bar
    # ------------------------------------------------------------------

    def contribute(self, status_bar_icons):
        """Put the widgets in the bar (``status_bar_icons``: the status-bar
        plugin's extension point), which owns their placement."""
        status_bar_icons.extend(
            [self.autosave_icon.control, self.navigator, self.protocol_chip]
        )

    def withdraw(self, status_bar_icons):
        """Stop following the protocol and take the widgets out of the bar,
        which deletes them."""
        widgets = [self.autosave_icon.control, self.navigator, self.protocol_chip]
        self.autosave_icon.model = None

        try:
            self._selection_model.currentChanged.disconnect(self._on_current_changed)
        except (RuntimeError, TypeError) as e:
            logger.debug(f"tree selection model already gone: {e}")

        self.trait_set(
            tree_pane=None,
            manager=None,
            tracker=None,
            status_model=None,
            sync=None,
            report=None,
            preferences=None,
            autosave_icon=None,
            navigator=None,
            protocol_chip=None,
            _steps=None,
            _selection_model=None,
        )

        for widget in widgets:
            if widget in status_bar_icons:
                status_bar_icons.remove(widget)

            else:
                # Never placed on a bar, so nothing else deletes it.
                widget.deleteLater()

    # ------------------------------------------------------------------
    # The step navigator
    # ------------------------------------------------------------------

    @observe("manager:rows_changed", dispatch="ui")
    def _structure_changed(self, event):
        self._steps = None
        self.show_step()

    @observe(
        "manager:selection.items, sync:free_mode, tracker:is_active", dispatch="ui"
    )
    @observe("status_model:[paused, current_step_path]", dispatch="ui")
    def _step_changed(self, event):
        self.show_step()

    def _on_current_changed(self, *_):
        self.show_step()

    def show_step(self):
        """Show the run's step while a run is active (paused included), else
        the tree's current row; ‹ › idle or paused, ⊘ idle only."""

        if self.navigator is None:
            return

        active = self.tracker.is_active
        paused = self.status_model.paused
        steps = self._navigable_steps()
        current = self.dock_pane.current_step_in(steps)

        self.navigator.show_step(
            self._run_text(paused) if active else self._idle_text(steps, current),
            navigable=not active or paused,
            deselectable=not active and self._tree().currentIndex().isValid(),
            can_previous=current is not None and current > 0,
            can_next=bool(steps) and (current is None or current < len(steps) - 1),
        )

    def _run_text(self, paused):
        """``Running · Step 2.1``, or Paused / Preview in its place."""
        preview = self.dock_pane.current_run_preview_mode
        state = "Paused" if paused else "Preview" if preview else "Running"
        row = self._row_at(self.status_model.current_step_path)

        return state if row is None else f"{state} · Step {row.dotted_path()}"

    def _idle_text(self, steps, current):
        """``Step 2.1 · 3/8 (+2 selected)``, a selected group's id, or Free
        Mode with nothing selected."""
        index = self._tree().currentIndex()
        row = None

        if index.isValid():
            row = self._row_at(self.tree_pane.widget.index_to_path(index))

        if row is None:
            return "Free Mode"

        if isinstance(row, GroupRow):
            return f"Group {row.dotted_path()}"

        text = f"Step {row.dotted_path()}"

        if current is not None:
            text += f" · {current + 1}/{len(steps)}"

        # Viewer edits land on every selected step; say so, as the viewer did.
        targets = len(write_back_targets(self.manager, row.uuid))

        if targets > 1:
            text += f" (+{targets - 1} selected)"

        return text

    def _row_at(self, path):
        """The protocol row at ``path``; None for no path or a stale one."""

        if not path:
            return None

        try:
            return self.manager.get_row(tuple(path))
        except IndexError:
            return None

    def _navigable_steps(self):
        """The tree pane's navigable steps, computed once per structure."""

        if self._steps is None:
            self._steps = self.tree_pane.navigable_steps()

        return self._steps

    def _tree(self):
        return self.tree_pane.widget.tree

    # ------------------------------------------------------------------
    # The protocol chip
    # ------------------------------------------------------------------

    @observe(
        "tracker:[protocol_name, loaded_protocol_path, is_modified]", dispatch="ui"
    )
    @observe("report:checks, preferences:preflight_enabled", dispatch="ui")
    def _protocol_changed(self, event):
        self.show_protocol()

    def show_protocol(self):
        """Show the protocol's name, file and state on the chip."""

        if self.protocol_chip is None:
            return

        tracker = self.tracker
        failure = self._electrodes_missing()

        self.protocol_chip.show_file(
            tracker.protocol_name,
            tracker.loaded_protocol_path or UNSAVED_PATH_NOTE,
            tracker.is_modified,
            "" if failure is None else failure.tooltip or failure.problem,
        )

    def _electrodes_missing(self):
        """The failed pre-flight check of protocol electrodes on the loaded
        device, if it failed (its result is the one source of truth); None
        otherwise."""

        if not self.preferences.preflight_enabled:
            return None

        return next(
            (
                check
                for check in self.report.checks
                if check.id == CHECK_ELECTRODES_EXIST and check.status == "fail"
            ),
            None,
        )

    def _open_protocol_menu(self):
        pane = self.dock_pane
        menu = chip_menu(self.protocol_chip)

        load = menu.addAction("Load…", pane.load_protocol_dialog)
        load.setEnabled(not self.tracker.is_active)
        menu.addAction("Save", pane.save_protocol_dialog)
        menu.addAction("Save as…", pane.save_as_protocol_dialog)
        menu.addSeparator()
        menu.addAction("Edit in protocol tree", self._raise_tree)

        open_menu_above(menu, self.protocol_chip)

    def _raise_tree(self):
        """Bring the protocol pane to the front and focus its tree."""
        pane = self.dock_pane
        pane.visible = True
        pane.control.raise_()

        self._tree().setFocus()
