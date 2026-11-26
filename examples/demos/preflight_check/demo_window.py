# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The demo window: a mock protocol navigation bar (as
``pluggable_protocol_tree/views/navigation_bar.py`` lays it out, plus mock
"Run selected" and "Preview" buttons), a placeholder for the protocol tree,
a Demo controls panel, and a mock status bar (as
``microdrop_utils.pyface_helpers.StatusBarManager`` builds it) with the
mode/step label, the pill right after it, and the bell on the right."""

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, Bool, Button, Enum, HasTraits, Instance, observe
from traitsui.api import Item, Label, VGroup, View

# Microdrop package imports.
from pluggable_protocol_tree.preflight.consts import UNUSED_COLUMN_PREFIX
from pluggable_protocol_tree.preflight.controller import PreflightController
from pluggable_protocol_tree.preflight.models import RunInfo
from pluggable_protocol_tree.preflight.views.panel import PreflightPanel
from pluggable_protocol_tree.preflight.views.pill import (
    PillController,
)
from pluggable_protocol_tree.services.preferences import ProtocolPreferences

# Microdrop style imports.
from microdrop_style.helpers import get_complete_stylesheet
from microdrop_style.icons.icons import (
    ICON_FIRST,
    ICON_LAST,
    ICON_NEXT,
    ICON_NOTIFICATIONS,
    ICON_PLAY,
    ICON_PREVIOUS,
    ICON_STOP,
)
from microdrop_style.label_style import get_label_style
from microdrop_style.palette_helpers import css, is_dark
from microdrop_style.panel_theme import (
    card_border,
    icon_button_style,
    muted_text,
    theme_palette,
)
from microdrop_style.status_bar_style import get_status_bar_stylesheet
from microdrop_style.typography import SECTION_TITLE, role_font

# Local imports.
from .mock_context import (
    SCENARIOS,
    SELECTED_PATHS,
    MockRig,
    SnapshotBinding,
    apply_scenario,
)
from .status_chips_proto import (
    ICON_SPACING,
    ProtocolDeviceChips,
    ProtocolMockState,
    StatusChipsBinding,
    StepNavigator,
    TintedPill,
    protocol_mock_view,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: How long a status-bar message stays, ms.
MESSAGE_MS = 3000

#: Simulated run: one tick a second, a step every few ticks.
TICK_MS = 1000
SECONDS_PER_STEP = 4

#: StatusBarManager's margins (microdrop_status_bar/consts.py).
STATUS_BAR_CONTENTS_MARGINS = (30, 0, 30, 0)

#: The step the editing mode shows.
EDITING_STEP = 3


class DemoControls(HasTraits):
    """Scenario, live toggles, mode and mutes over the mock state."""

    #: The canned scenario applied to the rig.
    scenario = Enum(*SCENARIOS)

    #: The status bar's mode when no protocol runs.
    mode = Enum("Free Mode", "Editing")

    #: Flip the pill and card to a run in progress.
    simulate_running = Bool(False)

    #: Drop the "this run" mutes.
    reset_mutes = Button("Reset mutes")

    #: Empty the persisted always-allowed list.
    clear_always_allowed = Button("Clear always-allowed")

    #: The state flipped.
    rig = Instance(MockRig)
    controller = Instance(PreflightController)
    run_info = Instance(RunInfo)

    @observe("scenario, rig")
    def _apply_scenario(self, event):
        if self.rig is not None:
            apply_scenario(self.rig, self.scenario)

    @observe("simulate_running")
    def _update_running(self, event):
        info = self.run_info

        if self.simulate_running and not info.step_total:
            info.trait_set(step=1, step_total=self.controller.report.step_count)

        info.active = self.simulate_running

    @observe("reset_mutes")
    def _reset_mutes(self, event):
        self.controller.clear_run_mutes()

    @observe("clear_always_allowed")
    def _clear_always_allowed(self, event):
        self.controller.preferences.preflight_always_allowed = []


demo_controls_view = View(
    VGroup(
        Item("scenario", show_label=False),
        Label("Live state"),
        Item("object.rig.dropbot_connected", label="DropBot connected"),
        Item("object.rig.hv_powered", label="HV power"),
        Item("object.rig.chip_inserted", label="Chip inserted"),
        Item("object.rig.camera_present", label="Camera present"),
        Item("object.rig.heater_connected", label="Heater connected"),
        Item("object.rig.magnet_connected", label="Magnet connected"),
        Item("object.rig.folder_writable", label="Folder writable"),
        Item("object.rig.free_disk_gb", label="Free disk (GB)"),
        Item("object.rig.toggled_columns_unused", label="Video/Heater unused"),
        Label("Run"),
        Item("simulate_running", label="Simulate running"),
        Item("reset_mutes", show_label=False),
        Item("clear_always_allowed", show_label=False),
    ),
)


class _StatusLabelBinding(HasTraits):
    """Keeps the status bar's mode/step label as the app sets it."""

    #: The mode chosen and the run in progress.
    controls = Instance(DemoControls)
    run_info = Instance(RunInfo)

    #: The label (a QLabel).
    label = Any()

    @observe("controls.mode, run_info.[active, step], label")
    def _show_mode(self, event):
        if None in (self.label, self.controls, self.run_info):
            return

        if self.run_info.active:
            self.label.setText(f"Running Protocol: Step {self.run_info.step}")

        elif self.controls.mode == "Editing":
            self.label.setText(f"Editing: Step {EDITING_STEP}")

        else:
            self.label.setText("Free Mode")


class PreflightDemoWindow(QtWidgets.QMainWindow):
    """The whole demo."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("MicroDrop — pre-flight check demo")
        self.resize(1000, 620)

        # The real helper on an in-memory node: nothing is saved.
        self.preferences = ProtocolPreferences(preferences=Preferences())
        self.rig = MockRig()
        self.controller = PreflightController(
            column_handlers=self.rig.column_handlers, preferences=self.preferences
        )
        self.snapshots = SnapshotBinding(rig=self.rig, controller=self.controller)
        self.controller.context_provider = self.snapshots.snapshot
        self.run_info = RunInfo()
        report = self.controller.report
        self.controls = DemoControls(
            rig=self.rig, controller=self.controller, run_info=self.run_info
        )

        self.protocol_state = ProtocolMockState()
        self.pill = TintedPill()
        self.pill.clicked.connect(self.toggle_popover)
        self._pill_controller = PillController(
            report=report,
            run_info=self.run_info,
            pill=self.pill,
            controller=self.controller,
        )

        self.popover = PreflightPanel(self.controller, self.run_info, parent=self)
        self.popover.run_requested.connect(self._on_panel_run)

        self._tick_timer = QtCore.QTimer(self, interval=TICK_MS)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        central = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._main_area(), 1)
        layout.addWidget(self._controls_panel())
        self.setCentralWidget(central)

        self._build_status_bar()
        self._chips_binding = StatusChipsBinding(
            state=self.protocol_state,
            run_info=self.run_info,
            chip=self.protocol_chip,
            navigator=self.navigator,
        )
        self._chips_binding.connect()

        self.controller.evaluate(self.snapshots.snapshot())

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _main_area(self):
        palette = theme_palette()
        theme = "dark" if is_dark(palette) else "light"

        area = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tree = QtWidgets.QLabel("Protocol tree goes here")
        tree.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tree.setStyleSheet(f"color: {css(muted_text(palette))};")

        # Same order and sheet as the real NavigationBar, plus the two mock
        # run scopes beside Play.
        navigation = QtWidgets.QWidget()
        navigation.setStyleSheet(get_complete_stylesheet(theme, "default"))
        buttons = QtWidgets.QHBoxLayout(navigation)
        buttons.setContentsMargins(5, 0, 5, 4)
        buttons.setSpacing(5)

        selected = ", ".join(str(path[0] + 1) for path in SELECTED_PATHS)

        for text, tooltip, slot in (
            (ICON_FIRST, "First Step", None),
            (ICON_PREVIOUS, "Previous Step", None),
            (ICON_PLAY, "Play Protocol", lambda: self._gate()),
            ("Run selected", f"Run steps {selected}", self._on_run_selected),
            ("Preview", "Preview the protocol", self._on_preview),
            (ICON_STOP, "Stop Protocol", self._on_stop_clicked),
            (ICON_NEXT, "Next Step", None),
            (ICON_LAST, "Last Step", None),
        ):
            button = QtWidgets.QPushButton(text)
            button.setToolTip(tooltip)
            button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

            if slot is not None:
                button.clicked.connect(slot)

            buttons.addWidget(button)

        layout.addWidget(tree, 1)
        layout.addWidget(navigation)

        return area

    def _controls_panel(self):
        palette = theme_palette()

        panel = QtWidgets.QFrame(objectName="demoControls")
        panel.setFixedWidth(280)
        panel.setStyleSheet(
            f"#demoControls {{ border-left: 1px solid {css(card_border(palette))}; }}"
        )
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)

        title = QtWidgets.QLabel("Demo controls")
        title.setFont(role_font(SECTION_TITLE))

        ui = self.controls.edit_traits(
            view=demo_controls_view, parent=panel, kind="subpanel"
        )

        layout.addWidget(title)
        protocol_ui = self.protocol_state.edit_traits(
            view=protocol_mock_view, parent=panel, kind="subpanel"
        )

        layout.addWidget(ui.control)
        layout.addWidget(protocol_ui.control)
        layout.addStretch(1)

        return panel

    def _build_status_bar(self):
        """After StatusBarManager.create_status_bar, reshaped by the status
        chips prototype: pill, step navigator and chips on the left, then
        the message and the bell on the right."""
        palette = theme_palette()
        theme = "dark" if is_dark(palette) else "light"
        status_bar = self.statusBar()
        status_bar.setContentsMargins(*STATUS_BAR_CONTENTS_MARGINS)
        status_bar.setStyleSheet(
            f"{get_status_bar_stylesheet(theme)}\n{get_label_style(theme)}"
        )

        self.center_label = QtWidgets.QLabel()
        self.center_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        bell = QtWidgets.QToolButton()
        bell.setText(ICON_NOTIFICATIONS)
        bell.setToolTip("Notifications (mock)")
        bell.setStyleSheet(icon_button_style(palette, 18))

        self.protocol_chip = ProtocolDeviceChips()
        self.protocol_chip.action_picked.connect(self.show_message)
        self.navigator = StepNavigator()
        self.persistent_label = self.navigator.label

        # Prototype row: pill, navigator and chips in one left cluster, then
        # a stretch, then message and bell on the right. The chips follow
        # the navigator's width naturally and elide before anything
        # overflows. The real port mounts the chips in StatusBarManager's
        # left slot, after the step navigator.
        row = QtWidgets.QWidget()
        grid = QtWidgets.QHBoxLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(ICON_SPACING)
        grid.addWidget(self.pill)
        grid.addWidget(self.navigator)
        grid.addWidget(self.protocol_chip)
        grid.addStretch(1)
        grid.addWidget(self.center_label)
        grid.addWidget(bell)

        status_bar.addWidget(row, 1)

        self._message_timer = QtCore.QTimer(self, singleShot=True)
        self._message_timer.timeout.connect(self.center_label.clear)

    # ------------------------------------------------------------------
    # Reactions
    # ------------------------------------------------------------------

    def open_popover(self):
        """Open the card upward from the pill."""
        self.popover.show_above(self.pill)

    def toggle_popover(self):
        """The pill's click: close the open card, else open it."""
        if self.popover.isVisible():
            self.popover.close()

        else:
            self.open_popover()

    def show_message(self, text):
        """A timed centre message, as StatusBarManager.show_center_message."""
        self.center_label.setText(text)
        self._message_timer.start(MESSAGE_MS)

    def _gate(self, run_paths=None, preview_mode=False, anyway=False):
        """The pre-run gate: snapshot the run asked for and evaluate it now,
        never trusting the idle report. All clear starts; "Run anyway"
        starts over warnings; anything else opens the card on the verdict."""
        if self.run_info.active:
            self.show_message("A protocol is already running")

            return

        self.snapshots.trait_set(run_paths=run_paths, preview_mode=preview_mode)
        report = self.controller.evaluate(self.snapshots.snapshot())

        if report.overall == "pass" or (anyway and report.overall == "warn"):
            if report.overall == "pass" and not anyway:
                self.pill.flash_all_clear()

            self._start_protocol(anyway)

            return

        self.open_popover()

    def _on_run_selected(self):
        self._gate(run_paths=SELECTED_PATHS)

    def _on_preview(self):
        self._gate(preview_mode=True)

    def _on_panel_run(self, anyway):
        """The card's Run / Run anyway: the same gate, same scope, again."""
        self._gate(self.snapshots.run_paths, self.snapshots.preview_mode, anyway)

    def _on_stop_clicked(self):
        self.controls.simulate_running = False

    def _start_protocol(self, anyway):
        report = self.controller.report
        skipped = [
            check.label
            for check in report.checks
            if check.id.startswith(f"{UNUSED_COLUMN_PREFIX}:")
            and report.is_muted(check)
        ]
        kind = "Preview" if self.snapshots.preview_mode else "Protocol"
        note = f" with {report.warning_count} warnings" if anyway else ""

        if skipped:
            note += f"; skipping {', '.join(skipped)} hooks"

        logger.info(f"{kind} started ({report.scope_line}){note}")
        self.show_message(f"{kind} started{note}")

        self.controller.clear_run_mutes()
        self.run_info.trait_set(step=1, step_total=report.step_count, elapsed_s=0)
        self.controls.simulate_running = True

    def _tick(self):
        info = self.run_info

        if not info.active or not info.step_total:
            return

        info.elapsed_s += 1

        if info.elapsed_s % SECONDS_PER_STEP == 0:
            info.step = info.step % info.step_total + 1
