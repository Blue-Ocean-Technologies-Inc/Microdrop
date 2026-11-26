# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Prototype of the status bar: the tinted pre-flight pill and a tight step
navigator on the left, followed by the protocol and device chips.

    [● Ready] ‹ Step 3/8 › ⊘ [▤ mixing-assay] [⬡ Chip-120]            🔔

The chips share the pill's status hues: green saved, amber unsaved, red
(protocol only) when the protocol uses electrodes the device lacks.

The card's header (summary, scope line) carries no protocol identity or
free-mode control today, so nothing here duplicates it; slimming the card
comes later."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, Int, Str, observe
from traitsui.api import Item, Label, VGroup, View

# Microdrop package imports.
from pluggable_protocol_tree.preflight.models import RunInfo
from pluggable_protocol_tree.preflight.views.pill import (
    ReadinessPill,
    status_color,
)

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_DESCRIPTION
from microdrop_style.palette_helpers import css, icon_font, with_alpha
from microdrop_style.panel_theme import (
    chip_text,
    icon_button_style,
    muted_text,
    theme_palette,
)
from microdrop_style.typography import CHIP, role_font

#: Height of every chip in the status bar, px.
CHIP_HEIGHT = 22

#: Widest a chip's name may grow before it elides, px.
NAME_MAX_WIDTH = 160

#: Background alpha of a saved (green) chip, and of an amber / red one.
SAVED_ALPHA = 0.11
ALERT_ALPHA = 0.14

#: How much stronger the wash grows on hover.
HOVER_BOOST = 0.09

#: Gap between the pill and the navigator, and between the two chips, px.
ICON_SPACING = 10
CHIP_GAP = 6

#: Glyph size of the navigator's buttons, px.
NAV_GLYPH_PX = 16

#: Glyphs (Material Symbols ligatures).
GLYPH_DEVICE = "developer_board"
GLYPH_MISMATCH = "warning"
GLYPH_PREVIOUS = "chevron_left"
GLYPH_NEXT = "chevron_right"
GLYPH_FREE_MODE = "block"

#: Chip state -> pill status whose colour it borrows, and its wash alpha.
CHIP_STATUS = {
    "saved": ("pass", SAVED_ALPHA),
    "unsaved": ("warn", ALERT_ALPHA),
    "mismatch": ("fail", ALERT_ALPHA),
}

#: Mock folders and recent files.
MOCK_PROTOCOL_FOLDER = "C:/Users/lab/Documents/MicroDrop/protocols"
MOCK_DEVICE_FOLDER = "C:/Users/lab/Documents/MicroDrop/devices"
RECENT_PROTOCOLS = ("pcr-prep", "elisa-wash", "droplet-split-test")
RECENT_DEVICES = ("Chip-90", "Chip-120-v2", "OpenDrop-v4")


def _chip_sheet(selector, accent, alpha, hover_alpha):
    """A fully rounded chip washed with ``accent``."""
    return (
        f"{selector} {{ background: {css(with_alpha(accent, alpha))};"
        f" border: none; border-radius: {CHIP_HEIGHT // 2}px; }}"
        f" {selector}:hover {{ background: {css(with_alpha(accent, hover_alpha))}; }}"
    )


def _menu_sheet(palette):
    """A compact, rounded menu."""
    text = palette.color(palette.ColorRole.Text)
    accent = status_color("pass", palette, on_card=False)

    return (
        "QMenu { padding: 4px; border-radius: 6px;"
        f" border: 1px solid {css(with_alpha(text, 0.15))}; }}"
        " QMenu::item { padding: 4px 18px 4px 12px; border-radius: 4px; }"
        f" QMenu::item:selected {{ background: {css(with_alpha(accent, 0.18))};"
        f" color: {css(text)}; }}"
        f" QMenu::item:disabled {{ color: {css(muted_text(palette))}; }}"
        " QMenu::separator { height: 1px; margin: 4px 8px;"
        f" background: {css(with_alpha(text, 0.12))}; }}"
    )


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

    #: The protocol uses electrodes the device lacks. The real version takes
    #: this from the pre-flight ``electrodes_exist`` check's result (one
    #: source of truth), never from a separate computation.
    mismatch = Bool(False)

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
        Item("mismatch", label="Protocol/device mismatch"),
        Item("step_count", label="Steps"),
    ),
)


class FileChip(QtWidgets.QFrame):
    """A rounded chip: glyph, elided name and an optional warning glyph,
    washed green (saved), amber (unsaved) or red (mismatch). The name's
    text style never changes: the wash and the tooltip carry the state."""

    #: Pressed.
    clicked = QtCore.Signal()

    def __init__(self, glyph, object_name, parent=None):
        super().__init__(parent)

        self.setObjectName(object_name)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(CHIP_HEIGHT)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 10, 0)
        layout.setSpacing(5)

        self._icon = QtWidgets.QLabel(glyph)
        self._icon.setFont(icon_font(15))

        self._name = QtWidgets.QLabel()
        self._name.setFont(role_font(CHIP))
        self._name.setMinimumWidth(16)
        self._name.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        self._warning = QtWidgets.QLabel(GLYPH_MISMATCH)
        self._warning.setFont(icon_font(14))
        self._warning.hide()

        layout.addWidget(self._icon)
        layout.addWidget(self._name, 1)
        layout.addWidget(self._warning)

        self._full_name = ""
        self._state = "saved"

    def set_name(self, name, path, unsaved, mismatch=False):
        """Show ``name`` (elided) in the colour of its state; a mismatch
        outranks unsaved changes."""
        self._full_name = name or "Untitled"
        self._state = "mismatch" if mismatch else "unsaved" if unsaved else "saved"

        self._warning.setVisible(mismatch)

        notes = []

        if mismatch:
            notes.append("Protocol uses electrodes not on this device")

        if unsaved:
            notes.append("Unsaved changes")

        self.setToolTip("\n".join([path, *notes]))
        self._restyle()
        self._elide()
        self.updateGeometry()

    def sizeHint(self):
        layout = self.layout()
        margins = layout.contentsMargins()
        metrics = self._name.fontMetrics()
        name_width = min(metrics.horizontalAdvance(self._full_name), NAME_MAX_WIDTH)
        width = (
            margins.left()
            + self._icon.sizeHint().width()
            + layout.spacing()
            + name_width
            + 2
            + margins.right()
        )

        if self._warning.isVisibleTo(self):
            width += layout.spacing() + self._warning.sizeHint().width()

        return QtCore.QSize(width, CHIP_HEIGHT)

    def minimumSizeHint(self):
        return QtCore.QSize(min(self.sizeHint().width(), 56), CHIP_HEIGHT)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def _elide(self):
        metrics = self._name.fontMetrics()
        self._name.setText(
            metrics.elidedText(
                self._full_name,
                QtCore.Qt.TextElideMode.ElideRight,
                max(self._name.width(), 1),
            )
        )

    def _restyle(self):
        palette = theme_palette()
        status, alpha = CHIP_STATUS[self._state]
        accent = status_color(status, palette, on_card=False)
        text = f"color: {css(chip_text(accent, palette))};"

        for label in (self._icon, self._name, self._warning):
            label.setStyleSheet(text)

        self.setStyleSheet(
            _chip_sheet(f"#{self.objectName()}", accent, alpha, alpha + HOVER_BOOST)
        )


class ProtocolDeviceChips(QtWidgets.QWidget):
    """The protocol and device chips, 6 px apart, each eliding on its own
    and opening its own menu. In the real app these mount in the left slot of
    ``StatusBarManager``, after the step navigator."""

    #: An action picked, as the text to show in the status bar.
    action_picked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(CHIP_GAP)

        self.protocol = FileChip(ICON_DESCRIPTION, "protocolChip")
        self.device = FileChip(GLYPH_DEVICE, "deviceChip")

        layout.addWidget(self.protocol, 1)
        layout.addWidget(self.device, 1)

        self.protocol.clicked.connect(
            lambda: self._open(self._protocol_menu(), self.protocol)
        )
        self.device.clicked.connect(
            lambda: self._open(self._device_menu(), self.device)
        )

    def set_state(self, state):
        """Show ``state``'s protocol and device: names, dirtiness, match."""
        self.protocol.set_name(
            state.name,
            f"{MOCK_PROTOCOL_FOLDER}/{state.name}.json",
            state.protocol_unsaved,
            state.mismatch,
        )
        self.device.set_name(
            state.device,
            f"{MOCK_DEVICE_FOLDER}/{state.device}.svg",
            state.device_unsaved,
        )
        self.updateGeometry()

    def _protocol_menu(self):
        menu = self._menu()

        for label in ("Load…", "Save", "Save as…", "Edit in protocol tree"):
            menu.addAction(label, lambda label=label: self._pick(label))

        self._recent(menu, "Recent", RECENT_PROTOCOLS)

        return menu

    def _device_menu(self):
        menu = self._menu()

        for label in ("Change device…", "Save device"):
            menu.addAction(label, lambda label=label: self._pick(label))

        self._recent(menu, "Recent devices", RECENT_DEVICES)

        return menu

    def _menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(_menu_sheet(theme_palette()))

        return menu

    def _recent(self, menu, title, names):
        recent = menu.addMenu(title)
        recent.setStyleSheet(menu.styleSheet())

        for name in names:
            recent.addAction(name, lambda name=name: self._pick(f"Open {name}"))

    def _open(self, menu, chip):
        """Open ``menu`` upward over ``chip``, as the card does from the
        pill."""
        height = menu.sizeHint().height()
        menu.exec(chip.mapToGlobal(QtCore.QPoint(0, -height - 4)))

    def _pick(self, label):
        self.action_picked.emit(f"{label} (mock)")


class TintedPill(ReadinessPill):
    """The pre-flight pill on a soft status-colour wash, as tall as the
    chips."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(CHIP_HEIGHT)

    def _paint(self, glyph, text, status, strong=False):
        super()._paint(glyph, text, status, strong)

        accent = status_color(status, theme_palette(), on_card=False)
        alpha = SAVED_ALPHA * (1.8 if strong else 1.0)
        self.setStyleSheet(
            _chip_sheet("#preflightPill", accent, alpha, alpha + HOVER_BOOST)
        )


class StepNavigator(QtWidgets.QWidget):
    """``‹ Step 3/8 › ⊘``: tight, flat glyph buttons as tall as the chips."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        style = (
            f"{icon_button_style(theme_palette(), NAV_GLYPH_PX)}"
            " QToolButton { padding: 0px; }"
        )

        self.previous = QtWidgets.QToolButton(text=GLYPH_PREVIOUS)
        self.previous.setToolTip("Previous step")

        self.label = QtWidgets.QLabel()

        self.next = QtWidgets.QToolButton(text=GLYPH_NEXT)
        self.next.setToolTip("Next step")

        self.free_mode = QtWidgets.QToolButton(text=GLYPH_FREE_MODE)
        self.free_mode.setToolTip("Deselect: back to free mode")

        for button in (self.previous, self.next, self.free_mode):
            button.setStyleSheet(style)
            button.setFixedSize(CHIP_HEIGHT, CHIP_HEIGHT)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self.previous)
        layout.addWidget(self.label)
        layout.addWidget(self.next)
        layout.addSpacing(2)
        layout.addWidget(self.free_mode)


class StatusChipsBinding(HasTraits):
    """Keeps the chips and navigator in step with the mock state and run,
    and steps the state from the navigator's buttons."""

    #: The mock protocol/device and the run.
    state = Instance(ProtocolMockState)
    run_info = Instance(RunInfo)

    #: The widgets (a ProtocolDeviceChips and a StepNavigator).
    chip = Any()
    navigator = Any()

    def connect(self):
        """Wire the navigator's buttons to the state."""
        self.navigator.previous.clicked.connect(lambda: self._step_by(-1))
        self.navigator.next.clicked.connect(lambda: self._step_by(1))
        self.navigator.free_mode.clicked.connect(
            lambda: setattr(self.state, "current_step", 0)
        )

    def _step_by(self, delta):
        state = self.state
        state.current_step = min(max(state.current_step + delta, 0), state.step_count)

    @observe("state.[name, protocol_unsaved, device, device_unsaved, mismatch], chip")
    def _show_identity(self, event):
        if None not in (self.chip, self.state):
            self.chip.set_state(self.state)

    @observe("state.[current_step, step_count], run_info.[active, step], navigator")
    def _show_step(self, event):
        if None in (self.navigator, self.state, self.run_info):
            return

        navigator = self.navigator
        state = self.state
        running = self.run_info.active

        if running:
            navigator.label.setText(f"Running Protocol: Step {self.run_info.step}")

        elif state.current_step:
            navigator.label.setText(f"Step {state.current_step}/{state.step_count}")

        else:
            navigator.label.setText("Free Mode")

        navigator.previous.setVisible(not running)
        navigator.next.setVisible(not running)
        navigator.free_mode.setVisible(not running and state.current_step > 0)
        navigator.previous.setEnabled(state.current_step > 0)
        navigator.next.setEnabled(state.current_step < state.step_count)
