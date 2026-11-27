# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The demo's protocol and device, shown by the real step navigator and file
chips: a mock state with live toggles, and the binding that keeps the
widgets in step with it and the run, as ``ProtocolStatusBarWidgets`` and
``DeviceChipController`` do in the app.

    [● Ready] ‹ Step 3 · 3/8 › ⊘ [▤ mixing-assay] [⬡ Chip-120]            🔔
"""

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Instance, Int, Str, observe
from traitsui.api import Item, Label, VGroup, View

# Microdrop package imports.
from device_viewer.views.device_chip import NO_DEVICE, NO_DEVICE_NOTE
from pluggable_protocol_tree.preflight.consts import CHECK_ELECTRODES_EXIST
from pluggable_protocol_tree.preflight.models import PreflightReport, RunInfo
from pluggable_protocol_tree.views.status_bar_widgets import StepNavigator

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_DESCRIPTION, ICON_DEVELOPER_BOARD

# Microdrop utils imports.
from microdrop_utils.status_chip import FileChip, chip_menu, open_menu_above

#: Mock folders the files live in.
MOCK_PROTOCOL_FOLDER = "C:/Users/lab/Documents/MicroDrop/protocols"
MOCK_DEVICE_FOLDER = "C:/Users/lab/Documents/MicroDrop/devices"

#: The chips' menus, as the app's.
PROTOCOL_ACTIONS = ("Load…", "Save", "Save as…", "Edit in protocol tree")
DEVICE_ACTIONS = ("Change device…", "Save device", "Save device as…")


class ProtocolMockState(HasTraits):
    """The protocol and device the status bar shows."""

    #: The protocol's file name, without extension.
    name = Str("mixing-assay")

    #: Protocol edits not yet saved.
    protocol_unsaved = Bool(True)

    #: The device's name.
    device = Str("Chip-120")

    #: Device edits not yet saved.
    device_unsaved = Bool(False)

    #: Steps in the protocol.
    step_count = Int(8)

    #: The selected step, 1-based; 0 is free mode.
    current_step = Int(3)

    @observe("step_count")
    def _clamp_step(self, event):
        self.step_count = max(self.step_count, 1)
        self.current_step = min(self.current_step, self.step_count)


protocol_mock_view = View(
    VGroup(
        Label("Protocol / device"),
        Item("name", label="Protocol"),
        Item("protocol_unsaved", label="Protocol unsaved"),
        Item("device", label="Device"),
        Item("device_unsaved", label="Device unsaved"),
        Item("step_count", label="Steps"),
    ),
)


class MockStatusBarBinding(HasTraits):
    """Keeps the navigator and chips in step with the mock state, the run
    and the pre-flight report, and steps the state from the navigator."""

    #: The mock protocol/device, the run and the pre-flight report (whose
    #: electrodes check is the chip's one source of error).
    state = Instance(ProtocolMockState)
    run_info = Instance(RunInfo)
    report = Instance(PreflightReport)

    #: The widgets (StepNavigator, and the protocol and device FileChips).
    navigator = Instance(StepNavigator)
    protocol_chip = Instance(FileChip)
    device_chip = Instance(FileChip)

    #: Called with the text of a menu action picked.
    show_message = Any()

    def traits_init(self):
        self.navigator = StepNavigator()
        self.protocol_chip = FileChip(ICON_DESCRIPTION, "protocolChip")
        self.device_chip = FileChip(ICON_DEVELOPER_BOARD, "deviceChip")

        self.navigator.previous.clicked.connect(lambda: self._step_by(-1))
        self.navigator.next.clicked.connect(lambda: self._step_by(1))
        self.navigator.free_mode.clicked.connect(
            lambda: setattr(self.state, "current_step", 0)
        )
        self.protocol_chip.clicked.connect(
            lambda: self._open(self.protocol_chip, PROTOCOL_ACTIONS)
        )
        self.device_chip.clicked.connect(
            lambda: self._open(self.device_chip, DEVICE_ACTIONS)
        )

    def _step_by(self, delta):
        state = self.state
        state.current_step = min(max(state.current_step + delta, 0), state.step_count)

    def _open(self, chip, actions):
        menu = chip_menu(chip)

        for label in actions:
            menu.addAction(label, lambda label=label: self._pick(label))

        open_menu_above(menu, chip)

    def _pick(self, label):
        if self.show_message is not None:
            self.show_message(f"{label} (mock)")

    @observe("state.[name, protocol_unsaved, device, device_unsaved]")
    @observe("report:checks, protocol_chip, device_chip")
    def _show_files(self, event):
        if None in (self.state, self.report, self.protocol_chip, self.device_chip):
            return

        state = self.state
        failure = next(
            (
                check
                for check in self.report.checks
                if check.id == CHECK_ELECTRODES_EXIST and check.status == "fail"
            ),
            None,
        )

        self.protocol_chip.show_file(
            state.name,
            f"{MOCK_PROTOCOL_FOLDER}/{state.name}.json",
            state.protocol_unsaved,
            "" if failure is None else failure.tooltip or failure.problem,
        )

        if not state.device:
            self.device_chip.show_neutral(NO_DEVICE, NO_DEVICE_NOTE)

            return

        self.device_chip.show_file(
            state.device,
            f"{MOCK_DEVICE_FOLDER}/{state.device}.svg",
            state.device_unsaved,
        )

    @observe("state.[current_step, step_count], run_info.[active, paused, step]")
    @observe("navigator")
    def _show_step(self, event):
        if None in (self.navigator, self.state, self.run_info):
            return

        current = self.state.current_step
        count = self.state.step_count
        run = self.run_info

        if run.active:
            state = "Paused" if run.paused else "Running"
            text = f"{state} · Step {run.step}"

        elif current:
            text = f"Step {current} · {current}/{count}"

        else:
            text = "Free Mode"

        self.navigator.show_step(
            text,
            navigable=not run.active or run.paused,
            deselectable=not run.active and current > 0,
            can_previous=current > 1,
            can_next=current < count,
        )
