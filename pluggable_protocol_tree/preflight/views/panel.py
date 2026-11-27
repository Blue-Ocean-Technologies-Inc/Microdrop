# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pill's card: a small panel opening upward from the status bar, in
the notifications drawer's surface, radius, type and motion.

Idle, it is the pre-flight check: a one-line header (summary, run scope),
the problems only (blocking, then warnings), one quiet line counting what
passed or was muted that expands to the full grouped list, and the Run
footer, always present. It opens on the current results at once; on a
refresh, only rows new since the last display fade in. While a protocol
runs, it shows only the step (N/total) and the elapsed time; the status
bar's label already says "Running Protocol". The header's gear flips it
to the settings face, whose ack waits are edited in place and saved when
the face goes; a run starting or ending flips it back.
Closes on Esc, the × button, the pill or click-away.
"""

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.panel_metrics import (
    DRAWER_PADDING_PX,
    DRAWER_RADIUS,
    DRAWER_SLIDE_MS,
)
from microdrop_style.panel_theme import theme_palette

# Local imports.
from ..consts import CATEGORIES, run_mute_key
from ..models import PreflightReport, RunInfo
from .panel_parts import fade_in, footer, header, quiet_line, run_info_rows, scrolling
from .panel_placement import PanelPlacement
from .rows import CheckRow, group_label
from .settings_face import settings_face
from .view_consts import GROUP_GAP, PANEL_WIDTH, ROW_GAP, SLIDE_PX

_ROLE = QtGui.QPalette.ColorRole
_RUNNING = QtCore.QAbstractAnimation.State.Running


class _PanelBinding(HasTraits):
    """Refreshes its panel when the report or the run changes."""

    #: The pre-flight report and the run shown.
    report = Instance(PreflightReport)
    run_info = Instance(RunInfo)

    #: The panel refreshed.
    panel = Any()

    @observe("report:run_mutes:items, report:always_mutes:items")
    @observe("report:checks")
    @observe("run_info:[active, step, step_total, elapsed_s]")
    def _refresh(self, event):
        self.panel.schedule_refresh()

    @observe("run_info:active")
    def _leave_settings_face(self, event):
        self.panel.show_checks_face()


class PreflightPanel(QtWidgets.QWidget):
    """The panel; ``show_above(pill)`` opens it.

    Like the notifications drawer, it is a child laid over its main window
    (``parent``), not a top-level popup, so it never leaves the window: it
    is clamped inside the window's content rect and, when its rows do not
    fit above the pill, they scroll between the fixed header and footer.
    """

    #: Emitted with True for "Run anyway", False for Run on an all-clear.
    run_requested = QtCore.Signal(bool)

    #: Emitted, the card closed, for the Settings dialog's protocol tab.
    settings_requested = QtCore.Signal()

    def __init__(self, controller, run_info, parent=None):
        super().__init__(parent)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(PANEL_WIDTH)

        self.controller = controller
        self.report = controller.report
        self.run_info = run_info
        self._expanded = False
        self._refresh_pending = False

        #: Keys of the problem rows last displayed; None until the first
        #: display, which never animates.
        self._displayed = None

        #: Whether the next refresh is the opening one: no entrances.
        self._opening_refresh = False

        #: Whether the settings face shows, and its embedded editor's UI.
        self._settings_face = False
        self._settings_ui = None

        #: The ack waits as the settings face opened on: what an edit there
        #: is told by. None while it is not shown.
        self._ack_times_opened = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(*[DRAWER_PADDING_PX] * 4)
        self._layout.setSpacing(0)
        self._content = None

        #: The scrolling rows, and the height of what never scrolls (the
        #: header, the footer and the gap above it).
        self._scroll = None
        self._fixed_height = 0

        # A child has no window opacity: the fade goes through an effect,
        # off once the panel is opaque.
        self._opacity = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity.setEnabled(False)
        self.setGraphicsEffect(self._opacity)

        self._placement = PanelPlacement(self, self._place)
        self._opening = self._open_animation()
        self._binding = _PanelBinding(report=self.report, run_info=run_info, panel=self)

        # A child shows with its parent unless hidden.
        self.hide()

    def detach(self):
        """Stop following the report, the run and the window, as before
        deletion."""
        self.close()
        self._dispose_settings()
        self._placement.release()
        self._binding.trait_set(report=None, run_info=None)

    # ------------------------------------------------------------------
    # Showing
    # ------------------------------------------------------------------

    def show_above(self, anchor):
        """Open upward from ``anchor``, left edges aligned, sliding up and
        fading in like the notifications drawer, on the current results."""
        self._placement.watch(anchor)
        self._opening.stop()
        self._opening_refresh = True
        self._settings_face = False
        self.refresh()

        end = self._place()
        slide, fade = self._opening.animationAt(0), self._opening.animationAt(1)
        slide.setStartValue(end + QtCore.QPoint(0, SLIDE_PX))
        slide.setEndValue(end)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)

        self._opacity.setOpacity(0.0)
        self._opacity.setEnabled(True)
        self.move(end + QtCore.QPoint(0, SLIDE_PX))
        self.show()
        self.raise_()
        self.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)
        self._opening.start()

    def _open_animation(self):
        group = QtCore.QParallelAnimationGroup(self)

        for target, prop in ((self, b"pos"), (self._opacity, b"opacity")):
            animation = QtCore.QPropertyAnimation(target, prop, self)
            animation.setDuration(DRAWER_SLIDE_MS)
            animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            group.addAnimation(animation)

        group.finished.connect(lambda: self._opacity.setEnabled(False))

        return group

    def _place(self):
        """Size and place the panel above its anchor; return its top-left.
        Mid-opening, only where the slide ends moves."""
        if self._placement.anchor is None or self.parentWidget() is None:
            return self.pos()

        end, height = self._placement.target(self._fit_height)
        self.setFixedHeight(height)

        if self._opening.state() == _RUNNING:
            slide = self._opening.animationAt(0)
            slide.setStartValue(end + QtCore.QPoint(0, SLIDE_PX))
            slide.setEndValue(end)

        else:
            self.move(end)

        return end

    def _fit_height(self, room):
        """The panel's height within ``room``: its natural height, else the
        rows scroll and the header and footer keep theirs."""
        if self._scroll is None:
            return min(self.sizeHint().height(), room)

        body = self._scroll.widget()
        body.ensurePolished()
        width = PANEL_WIDTH - 2 * DRAWER_PADDING_PX

        body_height = (
            body.heightForWidth(width)
            if body.hasHeightForWidth()
            else body.sizeHint().height()
        )
        chrome = 2 * DRAWER_PADDING_PX + self._fixed_height
        scroll_height = max(min(body_height, room - chrome), 0)
        self._scroll.setFixedHeight(scroll_height)

        return chrome + scroll_height

    def hideEvent(self, event):
        self._opening.stop()
        self._opacity.setEnabled(False)
        self._save_settings_edits()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.close()

            return

        super().keyPressEvent(event)

    def paintEvent(self, event):
        """The drawer's surface: window colour, hairline Mid border, rounded."""
        palette = theme_palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        painter.setPen(QtGui.QPen(palette.color(_ROLE.Mid)))
        painter.setBrush(palette.color(_ROLE.Window))
        painter.drawRoundedRect(rect, DRAWER_RADIUS, DRAWER_RADIUS)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def schedule_refresh(self):
        """Rebuild once, soon, if open on the checks: an ack edit on the
        settings face changes the report, and a rebuild would kill its
        spinbox mid-edit."""
        if self.isVisible() and not self._settings_face and not self._refresh_pending:
            self._refresh_pending = True
            QtCore.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        """Rebuild the panel from the report or the run, keeping its bottom
        on the anchor and its scroll position."""
        self._refresh_pending = False
        palette = theme_palette()
        scrolled = 0

        if self._scroll is not None:
            scrolled = self._scroll.verticalScrollBar().value()

        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.hide()
            self._content.deleteLater()

        self._dispose_settings()

        self._content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self._content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        if self._settings_face:
            face, self._settings_ui = settings_face(
                self.controller.preferences,
                palette,
                partial(self._flip_face, False),
                self._request_settings,
            )
            layout.addWidget(face)
            self._scroll = None

        elif self.run_info.active:
            for row in run_info_rows(self.run_info, palette):
                body_layout.addWidget(row)

            self._scroll = scrolling(body)
            layout.addWidget(self._scroll)
            self._fixed_height = 0

        else:
            self._build_checks(layout, body, body_layout, palette)

        self._layout.addWidget(self._content)
        self._place()

        if self._scroll is not None:
            self._scroll.verticalScrollBar().setValue(scrolled)

    def _build_checks(self, layout, body, body_layout, palette):
        """The header, the scrolling rows, and the footer below them."""
        report = self.report
        gear = partial(self._flip_face, True)
        top = header(report.summary, report.scope_line, palette, self.close, gear)
        shown = set()

        for check in report.problems():
            key = (check.id, run_mute_key(check.id, check.detail))
            row = self._row(check, card=True)

            if self._displayed is not None and key not in self._displayed:
                if not self._opening_refresh:
                    fade_in(row)

            shown.add(key)
            body_layout.addSpacing(ROW_GAP)
            body_layout.addWidget(row)

        self._displayed = shown
        self._opening_refresh = False

        body_layout.addSpacing(ROW_GAP)
        body_layout.addWidget(
            quiet_line(report, self._expanded, palette, self._toggle_expanded)
        )

        if self._expanded:
            self._build_expanded(body_layout, palette)

        # Always there: whatever opened the panel, it can start the run.
        bottom = footer(report, palette, self._request_run)

        self._scroll = scrolling(body)
        layout.addWidget(top)
        layout.addWidget(self._scroll)
        layout.addSpacing(DRAWER_PADDING_PX)
        layout.addWidget(bottom)

        bottom.ensurePolished()
        self._fixed_height = (
            top.sizeHint().height() + DRAWER_PADDING_PX + bottom.sizeHint().height()
        )

    def _build_expanded(self, layout, palette):
        for category in CATEGORIES:
            checks = self.report.quiet_checks(category)

            if not checks:
                continue

            layout.addSpacing(GROUP_GAP)
            layout.addWidget(group_label(category, palette))

            for check in checks:
                layout.addWidget(self._row(check, card=False))

    def _row(self, check, card):
        row = CheckRow(check, muted=self.report.mute_scope(check), card=card)

        row.mute_requested.connect(self.controller.mute)
        row.unmute_requested.connect(self.controller.unmute)

        return row

    def _toggle_expanded(self):
        self._expanded = not self._expanded
        QtCore.QTimer.singleShot(0, self.refresh)

    def _request_run(self, anyway):
        self.close()
        self.run_requested.emit(anyway)

    def show_checks_face(self):
        """Leave the settings face for the checks or the run, which a run
        starting or ending changes under it."""
        if self._settings_face:
            self._flip_face(False)

    def _flip_face(self, settings):
        if settings:
            self._ack_times_opened = self._ack_times()

        else:
            self._save_settings_edits()

        # Deferred: the button clicked lives in the content rebuilt.
        self._settings_face = settings
        QtCore.QTimer.singleShot(0, self.refresh)

    def _ack_times(self):
        return dict(self.controller.preferences.protocol_tree_ack_times)

    def _save_settings_edits(self):
        """Save the application preferences if the settings face changed an
        ack wait: an edit there only reaches the preferences node."""
        opened, self._ack_times_opened = self._ack_times_opened, None

        if opened is not None and self._ack_times() != opened:
            self.controller.preferences.preferences.save()

    def _request_settings(self):
        # The dialog is modal: the card closes first.
        self.close()
        self.settings_requested.emit()

    def _dispose_settings(self):
        if self._settings_ui is not None:
            self._settings_ui.dispose()
            self._settings_ui = None
