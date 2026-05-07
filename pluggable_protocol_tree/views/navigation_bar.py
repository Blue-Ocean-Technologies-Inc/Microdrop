"""Navigation pane and status bar for the pluggable protocol tree.

Ported from ``protocol_grid/extra_ui_elements.py`` (legacy
``NavigationBar`` + ``StatusBar``). The legacy widgets stay in place
until PPT-9 deletes ``protocol_grid``; this module is the canonical
location going forward.
"""

from pyface.qt.QtCore import Qt, QTimer
from pyface.qt.QtGui import QAction
from pyface.qt.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from microdrop_style.button_styles import (
    BUTTON_SPACING, ICON_FONT_FAMILY, get_button_style,
)
from microdrop_style.colors import BLACK, GREY, SECONDARY_SHADE, WHITE
from microdrop_style.helpers import get_complete_stylesheet, is_dark_mode
from microdrop_style.icons.icons import (
    ICON_FIRST, ICON_LAST, ICON_NEXT, ICON_NEXT_PHASE, ICON_PAUSE,
    ICON_PLAY, ICON_PREVIOUS, ICON_PREVIOUS_PHASE, ICON_RESUME, ICON_STOP,
)

# Material Symbols ligature used while Preview Mode is armed —
# replaces the play-arrow glyph so the button reads as a "preview"
# action at a glance.
ICON_PREVIEW = "video_search"
from microdrop_utils.pyside_helpers import MarqueeLabel


class NavigationBar(QWidget):
    """Two-row toolbar: playback/step/phase buttons on top, plugin-fillable
    left slot on bottom.

    The play button can be split into a Prev-phase / Resume / Next-phase
    cluster via ``split_play_button_to_phase_controls`` for protocols
    being driven phase-by-phase.

    Styling matches the legacy ``protocol_grid`` NavigationBar exactly:
    ``nav_container`` gets the full app stylesheet (so the icon font and
    button look match the rest of MicroDrop), ``left_slot_container``
    gets the tool-button stylesheet. Both are re-applied on
    ``colorSchemeChanged`` via a deferred QTimer.singleShot — the OS
    palette flag is briefly stale at signal time, so we let the event
    loop drain before re-reading ``is_dark_mode()``.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Bar should hug its sizeHint vertically — only stretch
        # horizontally — so the tree fills the rest of the window
        # rather than the bar growing into empty space.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top row: navigation buttons.
        self.nav_container = QWidget()
        nav_layout = QHBoxLayout(self.nav_container)
        # Horizontal padding keeps the buttons off the edges; vertical
        # padding is zero so the bar doesn't add bands above/below.
        nav_layout.setContentsMargins(5, 0, 5, 0)
        nav_layout.setSpacing(BUTTON_SPACING)

        self.btn_first = QPushButton(ICON_FIRST)
        self.btn_first.setToolTip("First Step")

        self.btn_prev = QPushButton(ICON_PREVIOUS)
        self.btn_prev.setToolTip("Previous Step")

        self.btn_stop = QPushButton(ICON_STOP)
        self.btn_stop.setToolTip("Stop Protocol")
        self.btn_stop.setEnabled(False)

        self.btn_next = QPushButton(ICON_NEXT)
        self.btn_next.setToolTip("Next Step")

        self.btn_last = QPushButton(ICON_LAST)
        self.btn_last.setToolTip("Last Step")

        # Play is a QToolButton with a menu-button split: the main face
        # behaves like before (click → start/pause/resume the protocol),
        # while the dropdown arrow exposes the persistent run-mode
        # toggle Preview Mode (the legacy protocol_grid checkbox).
        # Droplet detection is owned by its own column now, so it
        # doesn't need a slot here.
        self.btn_play = QToolButton()
        self.btn_play.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_play.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_play.setText(ICON_PLAY)
        self.btn_play.setToolTip("Play Protocol")

        self.play_menu = QMenu(self.btn_play)

        self.action_preview = QAction("Preview Mode", self.play_menu)
        self.action_preview.setCheckable(True)
        self.action_preview.setToolTip(
            "Run the protocol without sending any hardware messages "
            "(useful when no DropBot is connected)"
        )

        self.play_menu.addAction(self.action_preview)
        self.btn_play.setMenu(self.play_menu)

        # Toggling Preview re-applies the play-button stylesheet (so
        # background + hover flip to yellow) and refreshes the play
        # state so the icon swaps to ``video_search`` and the tooltip
        # picks up the "Preview" wording.
        self.action_preview.toggled.connect(lambda _: self._on_preview_toggled())

        self.btn_prev_phase = QPushButton(ICON_PREVIOUS_PHASE)
        self.btn_prev_phase.setToolTip("Previous Phase")

        self.btn_resume = QPushButton(ICON_RESUME)
        self.btn_resume.setToolTip("Resume Protocol")

        self.btn_next_phase = QPushButton(ICON_NEXT_PHASE)
        self.btn_next_phase.setToolTip("Next Phase")

        self.play_phase_container = QWidget()
        self.play_phase_container.setObjectName("play_phase_subcontainer")
        self.play_phase_layout = QHBoxLayout(self.play_phase_container)
        self.play_phase_layout.setContentsMargins(0, 0, 0, 0)
        self.play_phase_layout.setSpacing(BUTTON_SPACING)

        self.play_phase_layout.addWidget(self.btn_play)
        for btn in (self.btn_prev_phase, self.btn_resume, self.btn_next_phase):
            btn.setVisible(False)
            self.play_phase_layout.addWidget(btn)

        all_buttons = [
            self.btn_first, self.btn_prev, self.btn_play, self.btn_stop,
            self.btn_next, self.btn_last,
            self.btn_prev_phase, self.btn_resume, self.btn_next_phase,
        ]
        for btn in all_buttons:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.play_phase_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed,
        )

        nav_layout.addWidget(self.btn_first)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.play_phase_container)
        nav_layout.addWidget(self.btn_stop)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_last)

        self._phase_navigation_active = False

        # Bottom row: plugin-fillable left slot.
        self.bottom_container = QWidget()
        bottom_layout = QHBoxLayout(self.bottom_container)
        # Same horizontal-only padding as the nav row.
        bottom_layout.setContentsMargins(5, 0, 5, 0)
        bottom_layout.setSpacing(10)

        self.left_slot_container = QWidget()
        self.left_slot_layout = QHBoxLayout(self.left_slot_container)
        self.left_slot_layout.setContentsMargins(0, 0, 0, 0)
        self.left_slot_layout.setSpacing(5)

        bottom_layout.addWidget(self.left_slot_container)
        bottom_layout.addStretch()

        main_layout.addWidget(self.nav_container)
        main_layout.addWidget(self.bottom_container)

        # The bottom row is dead space until a plugin contributes a
        # widget via add_widget_to_left_slot — keep it hidden so the
        # nav buttons sit flush against the tree.
        self.bottom_container.setVisible(False)

        # Apply the legacy protocol_grid stylesheet and re-apply on
        # OS theme changes.
        self.apply_styling()
        QApplication.styleHints().colorSchemeChanged.connect(
            self._on_color_scheme_changed,
        )

    def apply_styling(self):
        """Apply the same stylesheet the legacy protocol_grid uses for
        its NavigationBar: full app sheet on the nav button row, tool
        button sheet on the left-slot row.

        The play button is a QToolButton, which the default stylesheet
        only targets via its ``QPushButton`` rules — leaving the play
        button without the Material Symbols font (so the glyph name
        ``play_arrow`` renders as literal text). _play_btn_stylesheet
        applies a QToolButton-targeting equivalent so the icon font,
        colours, and hover behaviour all match its QPushButton siblings.
        """
        theme = "dark" if is_dark_mode() else "light"
        self.nav_container.setStyleSheet(
            get_complete_stylesheet(theme, "default"),
        )
        self.left_slot_container.setStyleSheet(
            get_button_style(theme, "tool"),
        )
        self.btn_play.setStyleSheet(self._play_btn_stylesheet(theme))

    def _play_btn_stylesheet(self, theme):
        """QToolButton stylesheet mirroring the default QPushButton look
        (icon font + theme-aware colours). When ``action_preview`` is
        checked the main face flips to a soft yellow so it's obvious
        at a glance that the next click won't touch hardware. The
        ``::menu-button`` arrow is kept deliberately subtle — no
        separator border, narrower width — so it doesn't compete
        visually with the main play face.
        """
        if theme == "dark":
            bg, fg, border = GREY['dark'], WHITE, GREY['lighter']
            bg_disabled = BLACK
            fg_disabled = GREY['light']
            border_disabled = GREY['dark']
            preview_bg, preview_border, preview_fg = "#a68f00", "#ffd54f", BLACK
            preview_hover_bg, preview_hover_border = "#bfa200", "#ffe082"
            normal_hover_bg = GREY['light']
            normal_hover_border = SECONDARY_SHADE[300]
            normal_hover_fg = SECONDARY_SHADE[700]
        else:
            bg, fg, border = WHITE, BLACK, GREY['light']
            bg_disabled = GREY['light']
            fg_disabled = GREY['dark']
            border_disabled = GREY['lighter']
            preview_bg, preview_border, preview_fg = "#fff59d", "#fbc02d", BLACK
            preview_hover_bg, preview_hover_border = "#ffe082", "#fb8c00"
            normal_hover_bg = GREY['light']
            normal_hover_border = SECONDARY_SHADE[300]
            normal_hover_fg = SECONDARY_SHADE[700]

        if self.action_preview.isChecked():
            bg, fg, border = preview_bg, preview_fg, preview_border
            hover_bg, hover_border, hover_fg = (
                preview_hover_bg, preview_hover_border, preview_fg,
            )
        else:
            hover_bg, hover_border, hover_fg = (
                normal_hover_bg, normal_hover_border, normal_hover_fg,
            )
        return f"""
            QToolButton {{
                font-family: "{ICON_FONT_FAMILY}";
                font-size: 22px;
                padding: 4px 8px;
                border-radius: 4px;
                min-width: 60px;
                min-height: 26px;
                border: 1px solid {border};
                background-color: {bg};
                color: {fg};
            }}
            QToolButton:hover {{
                color: {hover_fg};
                background-color: {hover_bg};
                border-color: {hover_border};
            }}
            QToolButton:pressed {{
                background-color: {GREY['dark']};
            }}
            QToolButton:disabled {{
                color: {fg_disabled};
                background-color: {bg_disabled};
                border-color: {border_disabled};
            }}
            QToolButton::menu-button {{
                border: none;
                background: transparent;
                width: 18px;
            }}
            QToolButton::menu-arrow {{
                width: 10px;
                height: 10px;
            }}
        """

    def is_preview_mode(self):
        """True when the user has armed Preview Mode in the play
        dropdown — the legacy ``preview_mode_checkbox.isChecked()``."""
        return self.action_preview.isChecked()

    def _on_preview_toggled(self):
        """Re-apply styling and refresh whichever play-button state is
        currently showing so the icon + tooltip flip to / from the
        preview variant. The pause/resume icons themselves don't need
        a per-toggle rewrite — only their tooltips read different text
        in preview — so reading the button's current text decides
        which show_* helper re-runs."""
        self.apply_styling()
        current_text = self.btn_play.text()
        if current_text == ICON_PAUSE:
            self.show_pause_state()
        elif current_text == ICON_RESUME:
            self.show_resume_state()
        else:
            self.show_play_state()

    def _on_color_scheme_changed(self, *_):
        """Defer the re-style by one event-loop tick — when this signal
        first fires, ``is_dark_mode()`` may still report the previous
        theme. A 0 ms timer pushes the work to after the OS flags
        settle. Mirrors the legacy widget.py:497 pattern verbatim."""
        QTimer.singleShot(0, self.apply_styling)

    def split_play_button_to_phase_controls(self):
        if self._phase_navigation_active:
            return
        self._phase_navigation_active = True
        self.btn_play.setVisible(False)
        self.btn_prev_phase.setVisible(True)
        self.btn_resume.setVisible(True)
        self.btn_next_phase.setVisible(True)
        self.play_phase_container.update()
        self.update()

    def merge_phase_controls_to_play_button(self):
        if not self._phase_navigation_active:
            return
        self._phase_navigation_active = False
        self.btn_prev_phase.setVisible(False)
        self.btn_resume.setVisible(False)
        self.btn_next_phase.setVisible(False)
        self.btn_play.setVisible(True)
        self.play_phase_container.update()
        self.update()

    def set_phase_navigation_enabled(self, prev_enabled, next_enabled):
        self.btn_prev_phase.setEnabled(prev_enabled)
        self.btn_next_phase.setEnabled(next_enabled)

    def is_phase_navigation_active(self):
        return self._phase_navigation_active

    def add_widget_to_left_slot(self, widget):
        """Helper for plugin-contributed widgets in the bottom-left area.
        Reveals the bottom container — it's hidden by default to avoid
        an empty band between the nav buttons and the tree."""
        self.left_slot_layout.addWidget(widget)
        self.bottom_container.setVisible(True)

    # --- play-button visual state -----------------------------------------
    #
    # Each show_*_state() reads ``action_preview.isChecked()`` and picks
    # the matching icon + tooltip — so toggling Preview Mode while the
    # button is in any state correctly relabels it. A "Preview" prefix
    # in the tooltip and the ``video_search`` glyph signal that the
    # next click won't drive hardware.

    def _preview_armed(self):
        return self.action_preview.isChecked()

    def show_play_state(self):
        """Idle: video_search + 'Preview Protocol' if armed, else
        play_arrow + 'Play Protocol'."""
        if self._preview_armed():
            self.btn_play.setText(ICON_PREVIEW)
            self.btn_play.setToolTip("Preview Protocol")
        else:
            self.btn_play.setText(ICON_PLAY)
            self.btn_play.setToolTip("Play Protocol")

    def show_pause_state(self):
        """Running: ⏸ icon. Tooltip notes preview state when armed."""
        self.btn_play.setText(ICON_PAUSE)
        self.btn_play.setToolTip(
            "Pause Preview" if self._preview_armed() else "Pause Protocol"
        )

    def show_resume_state(self):
        """Paused: ▶▶ icon. Tooltip notes preview state when armed."""
        self.btn_play.setText(ICON_RESUME)
        self.btn_play.setToolTip(
            "Resume Preview" if self._preview_armed() else "Resume Protocol"
        )


class StatusBar(QScrollArea):
    """Horizontal scrollable status row: total/step time, repeat
    counter, step progress, repetition counter, recent/next-step labels.

    All labels are exposed as public attributes so callers can update
    text directly (matches the legacy ``protocol_grid`` API).

    The recent/next step labels are MarqueeLabel instances with fixed
    widths — long step names truncate by default, but auto-scroll
    horizontally when the user hovers over the label.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        scroll_content = QWidget()
        layout = QHBoxLayout(scroll_content)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        self.lbl_total_time = QLabel("Total Time: 0 s")
        self.lbl_total_time.setFixedWidth(120)
        self.lbl_total_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_step_time = QLabel("Step Time: 0 s")
        self.lbl_step_time.setFixedWidth(115)
        self.lbl_step_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Phase time slot — not in the legacy StatusBar layout, but
        # callers (BasePluggableProtocolDemoWindow) want to surface
        # the per-phase ack timer here. Hidden by default; the demo
        # window reveals it iff DemoConfig.phase_ack_topic is set.
        self.lbl_phase_time = QLabel("Phase 0.00s / 0.00s")
        self.lbl_phase_time.setFixedWidth(170)
        self.lbl_phase_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_phase_time.setVisible(False)

        repeat_layout = QHBoxLayout()
        repeat_layout.setContentsMargins(0, 0, 0, 0)
        repeat_layout.setSpacing(2)

        self.lbl_repeat_protocol = QLabel("Repeat Protocol:")
        self.lbl_repeat_protocol.setFixedWidth(140)
        self.lbl_repeat_protocol.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_repeat_protocol_status = QLabel("0/")
        self.lbl_repeat_protocol_status.setFixedWidth(20)
        self.lbl_repeat_protocol_status.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter,
        )
        # Bounded integer input — replaces the legacy QLineEdit("1")
        # which let users type arbitrary text. SpinBox enforces the
        # int range and avoids needing a try/except on .text().
        self.edit_repeat_protocol = QSpinBox()
        self.edit_repeat_protocol.setRange(1, 999)
        self.edit_repeat_protocol.setValue(1)
        self.edit_repeat_protocol.setFixedWidth(50)
        self.edit_repeat_protocol.setAlignment(Qt.AlignCenter)
        self.edit_repeat_protocol.setFixedHeight(20)

        repeat_layout.addWidget(self.lbl_repeat_protocol)
        repeat_layout.addWidget(self.lbl_repeat_protocol_status)
        repeat_layout.addWidget(self.edit_repeat_protocol)

        repeat_widget = QWidget()
        repeat_widget.setLayout(repeat_layout)
        repeat_widget.setFixedWidth(190)
        repeat_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        repeat_widget.setFixedHeight(20)

        self.lbl_step_progress = QLabel("Step 0/0")
        self.lbl_step_progress.setFixedWidth(80)
        self.lbl_step_progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_step_repetition = QLabel("Repetition 0/0")
        self.lbl_step_repetition.setFixedWidth(100)
        self.lbl_step_repetition.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Recent / next step labels: fixed width truncates long step
        # names by default; on hover the MarqueeLabel auto-scrolls the
        # full text into view.
        self.lbl_recent_step = MarqueeLabel("Most Recent Step: -")
        self.lbl_recent_step.setFixedWidth(200)
        self.lbl_recent_step.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_next_step = MarqueeLabel("Next Step: -")
        self.lbl_next_step.setFixedWidth(180)
        self.lbl_next_step.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        for w in (
            self.lbl_total_time, self.lbl_step_time, self.lbl_phase_time,
            self.lbl_step_progress, self.lbl_step_repetition,
            self.lbl_recent_step, self.lbl_next_step,
        ):
            w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            w.setFixedHeight(20)

        layout.addWidget(self.lbl_total_time)
        layout.addWidget(self.lbl_step_time)
        layout.addWidget(self.lbl_phase_time)
        layout.addWidget(repeat_widget)
        layout.addWidget(self.lbl_step_progress)
        layout.addWidget(self.lbl_step_repetition)
        layout.addWidget(self.lbl_recent_step)
        layout.addWidget(self.lbl_next_step)
        layout.addStretch()

        self.setWidget(scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFixedHeight(40)

        self._apply_styling()
        QApplication.styleHints().colorSchemeChanged.connect(self._apply_styling)

    def _apply_styling(self):
        if is_dark_mode():
            text_color = WHITE
            input_style = f"""
                QSpinBox {{
                    color: {WHITE};
                    background-color: #2d2d2d;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 2px;
                }}
            """
        else:
            text_color = BLACK
            input_style = f"""
                QSpinBox {{
                    color: {BLACK};
                    background-color: white;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                    padding: 2px;
                }}
            """

        label_style = f"QLabel {{ color: {text_color}; }}"
        for label in (
            self.lbl_total_time, self.lbl_step_time, self.lbl_phase_time,
            self.lbl_repeat_protocol, self.lbl_repeat_protocol_status,
            self.lbl_step_progress, self.lbl_step_repetition,
            self.lbl_recent_step, self.lbl_next_step,
        ):
            label.setStyleSheet(label_style)
        self.edit_repeat_protocol.setStyleSheet(input_style)


def make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)
    return line
