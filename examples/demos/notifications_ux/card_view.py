# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One notification as a card, in the drawer or as a toast::

    ▌ (!)  Title, bold while unread                    •  ✕
    ▌      Source · 3 min ago · ×2
    ▌      Two lines of the detail, then an ellipsis…
    ▌      Show more
    ▌      [ Primary ]  How do I…?

A widget, not a painted delegate: it has real buttons, and the drawer lists
a few hundred at most. Runs standalone against just an entry::

    NotificationCard(UxNotification(title="Hello", detail="World")).show()

The card only reports clicks, through its signals; whoever holds it acts.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, observe

# Microdrop package imports.
from notifications.consts import SEVERITY_COLORS, SEVERITY_GLYPHS
from notifications.models.notification import Notification
from notifications.views.formatting import format_exact_time, format_preview

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR
from microdrop_style.icons.icons import ICON_CLOSE

# Local imports.
from .card_parts import ClampedLabel, NewDot, meta_text
from .ux_consts import CARD_BODY_LINES, HelpAction
from .view_styles import (
    card_border,
    card_fill,
    css,
    icon_button_style,
    icon_font,
    is_dark,
    link_button_style,
    muted_text,
    primary_button_style,
    quiet_button_style,
    rounded_path,
    text_font,
    with_alpha,
)

#: Width (px) of the severity stripe down a card's left edge.
STRIPE_WIDTH = 4

#: Pixel size of the severity glyph.
GLYPH_SIZE = 20

#: Height (px) of a toast's countdown line along the card's bottom.
PROGRESS_HEIGHT = 3

#: Most pixels an expanded traceback takes before it scrolls.
TRACEBACK_MAX_HEIGHT = 200

_ELIDE = QtCore.Qt.TextElideMode.ElideRight
_ALIGN = QtCore.Qt.AlignmentFlag
_PALETTE_EVENTS = (
    QtCore.QEvent.Type.PaletteChange,
    QtCore.QEvent.Type.ApplicationPaletteChange,
)


class _CardBinding(HasTraits):
    """Refreshes its card when the entry changes."""

    entry = Instance(Notification)

    card = Any()

    @observe("entry:changed")
    def _refresh(self, event):
        self.card.refresh()


class NotificationCard(QtWidgets.QFrame):
    """A notification card; ``toast`` cards are always bold, never marked
    new, and hand body clicks on rather than expanding."""

    #: The dismiss cross.
    dismiss_clicked = QtCore.Signal(object)

    #: The primary button.
    action_clicked = QtCore.Signal(object)

    #: The second button: a tutorial link or "Later".
    secondary_clicked = QtCore.Signal(object)

    #: "Show more" / "Show less", or a click on a drawer card's body.
    expand_clicked = QtCore.Signal(object)

    #: A click on a toast's body.
    body_clicked = QtCore.Signal(object)

    def __init__(self, entry, parent=None, toast=False):
        super().__init__(parent)

        self.entry = entry
        self.toast = toast

        #: A toast's time left, 0-1; None draws no countdown.
        self.progress = None

        self._hovered = False
        self._palette_key = None

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum
        )

        self._build()
        self._binding = _CardBinding(entry=entry, card=self)
        self._restyle()
        self.refresh()

    # ------------------------------------------------------------------ #
    # Building                                                            #
    # ------------------------------------------------------------------ #

    def _build(self):
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(STRIPE_WIDTH + 10, 10, 8, 11)
        outer.setSpacing(10)

        self._glyph = QtWidgets.QLabel(self)
        self._glyph.setFont(icon_font(GLYPH_SIZE))
        self._glyph.setFixedWidth(GLYPH_SIZE + 2)
        self._glyph.setAlignment(_ALIGN.AlignHCenter | _ALIGN.AlignTop)
        outer.addWidget(self._glyph, 0, _ALIGN.AlignTop)

        column = QtWidgets.QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        outer.addLayout(column, 1)

        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)

        self._title = QtWidgets.QLabel(self)
        self._title.setWordWrap(True)
        self._title.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        top.addWidget(self._title, 1, _ALIGN.AlignTop)

        self._new_dot = NewDot(self)
        top.addWidget(self._new_dot, 0, _ALIGN.AlignTop)

        self._dismiss = QtWidgets.QToolButton(self)
        self._dismiss.setText(ICON_CLOSE)
        self._dismiss.setToolTip(
            "Hide (it stays in notifications)" if self.toast else "Dismiss"
        )
        self._dismiss.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self._dismiss.clicked.connect(lambda: self.dismiss_clicked.emit(self.entry))
        top.addWidget(self._dismiss, 0, _ALIGN.AlignTop)
        column.addLayout(top)

        self._meta = QtWidgets.QLabel(self)
        self._meta.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed
        )
        column.addWidget(self._meta)

        column.addSpacing(4)

        self._body = ClampedLabel(self)
        self._body.overflow_changed.connect(self._show_more_link)
        column.addWidget(self._body)

        self._traceback = QtWidgets.QPlainTextEdit(self)
        self._traceback.setReadOnly(True)
        self._traceback.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._traceback.setFont(
            QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        )
        self._traceback.hide()
        column.addWidget(self._traceback)

        # The buttons, then "Show more" at the far end, on one row.
        self._footer = QtWidgets.QWidget(self)
        footer = QtWidgets.QHBoxLayout(self._footer)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(10)

        self._primary = QtWidgets.QPushButton(self._footer)
        self._primary.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._primary.clicked.connect(lambda: self.action_clicked.emit(self.entry))
        footer.addWidget(self._primary)

        self._secondary = QtWidgets.QPushButton(self._footer)
        self._secondary.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._secondary.clicked.connect(lambda: self.secondary_clicked.emit(self.entry))
        footer.addWidget(self._secondary)
        footer.addStretch(1)

        self._more = QtWidgets.QPushButton(self._footer)
        self._more.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._more.clicked.connect(lambda: self.expand_clicked.emit(self.entry))
        footer.addWidget(self._more)
        column.addWidget(self._footer)

        self._acted = QtWidgets.QLabel(self)
        column.addWidget(self._acted)

    # ------------------------------------------------------------------ #
    # Showing the entry                                                   #
    # ------------------------------------------------------------------ #

    def refresh(self):
        """Show the entry as it is now."""
        entry = self.entry
        palette = self.palette()

        self._glyph.setText(SEVERITY_GLYPHS[entry.severity])
        self._glyph.setStyleSheet(f"color: {SEVERITY_COLORS[entry.severity]};")

        bold = self.toast or entry.unread or entry.needs_attention
        self._title.setFont(
            text_font(
                self.font(),
                0.5,
                QtGui.QFont.Weight.DemiBold if bold else QtGui.QFont.Weight.Medium,
            )
        )
        self._title.setText(entry.title)

        self._new_dot.setVisible(not self.toast and entry.is_new)
        self.refresh_time()
        self._show_body()

        if entry.action is not None:
            self._primary.setText(entry.action.label)

        self._primary.setVisible(entry.action is not None and not entry.acted)

        secondary = entry.secondary_action

        if secondary is not None:
            self._secondary.setText(secondary.label)
            self._secondary.setToolTip(
                f"Open the tutorial: {secondary.tutorial}"
                if isinstance(secondary, HelpAction)
                else "Move this out of Needs attention, for later"
            )

        self._secondary.setVisible(secondary is not None and not entry.acted)
        self._style_secondary(palette)
        self._show_footer()

        self._acted.setVisible(bool(entry.acted))
        self._acted.setText(f"✓  {entry.acted}")

        self.setToolTip(self._tooltip())
        self.update()

    def refresh_time(self):
        """Show the time since the entry, which runs on."""
        metrics = QtGui.QFontMetrics(self._meta.font())
        text = meta_text(self.entry)

        self._meta.setText(
            metrics.elidedText(text, _ELIDE, max(self._meta.width(), 60))
        )

    def set_progress(self, progress):
        """Draw a toast's countdown at ``progress`` (0-1), or none."""

        if progress != self.progress:
            self.progress = progress
            self.update()

    def _show_body(self):
        entry = self.entry
        traceback = entry.monospace_detail
        expanded = entry.expanded and not self.toast

        self._body.setVisible(bool(entry.detail) and not (traceback and expanded))
        self._body.set_full_text(
            format_preview(entry) if traceback else entry.detail,
            lines=0 if expanded else CARD_BODY_LINES,
        )

        self._traceback.setVisible(traceback and expanded)

        if traceback and expanded:
            if self._traceback.toPlainText() != entry.detail:
                self._traceback.setPlainText(entry.detail)

            lines = entry.detail.count("\n") + 2
            metrics = QtGui.QFontMetrics(self._traceback.font())
            height = min(lines * metrics.lineSpacing() + 24, TRACEBACK_MAX_HEIGHT)
            self._traceback.setFixedHeight(height)

        self._show_more_link()

    def _show_more_link(self, *args):
        entry = self.entry
        expandable = entry.monospace_detail or self._body.overflowed or entry.expanded

        expandable = bool(entry.detail) and expandable

        self._more.setVisible(not self.toast and expandable)
        self._more.setText("Show less" if entry.expanded else "Show more")
        self._show_footer()

        # The hand only where a click does something.
        clickable = self.toast or expandable
        self.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
            if clickable
            else QtCore.Qt.CursorShape.ArrowCursor
        )

    def _show_footer(self):
        """The footer row shows while any of its buttons does; buttons get
        room above them."""
        buttons = not self._primary.isHidden() or not self._secondary.isHidden()

        self._footer.setVisible(buttons or not self._more.isHidden())
        self._footer.layout().setContentsMargins(0, 6 if buttons else 0, 0, 0)

    def _tooltip(self):
        entry = self.entry
        lines = [
            f"{entry.source or entry.category}",
            format_exact_time(entry.last_seen),
        ]

        if entry.count > 1:
            lines.append(
                f"{entry.count} times since {format_exact_time(entry.first_seen)}"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Style                                                               #
    # ------------------------------------------------------------------ #

    def _restyle(self):
        palette = self.palette()
        key = (
            palette.color(QtGui.QPalette.ColorRole.Window).rgba(),
            palette.color(QtGui.QPalette.ColorRole.Text).rgba(),
        )

        if key == self._palette_key:
            return

        self._palette_key = key
        muted = muted_text(palette)

        self._meta.setFont(text_font(self.font(), -1.0))
        self._meta.setStyleSheet(f"color: {muted.name()};")
        self._body.setStyleSheet(
            f"color: {palette.color(QtGui.QPalette.ColorRole.Text).name()};"
        )
        self._acted.setFont(text_font(self.font(), -0.5))
        self._acted.setStyleSheet(f"color: {muted.name()};")
        self._dismiss.setStyleSheet(icon_button_style(palette, 16))
        self._more.setStyleSheet(link_button_style(palette, INFO_COLOR))
        self._primary.setStyleSheet(primary_button_style())

        code_fill = with_alpha(palette.color(QtGui.QPalette.ColorRole.Text), 0.05)
        self._traceback.setStyleSheet(
            f"QPlainTextEdit {{ background: {css(code_fill)};"
            " border: none; border-radius: 4px; }"
        )
        self._style_secondary(palette)

    def _style_secondary(self, palette):
        if isinstance(self.entry.secondary_action, HelpAction):
            self._secondary.setStyleSheet(link_button_style(palette, INFO_COLOR))

        else:
            self._secondary.setStyleSheet(quiet_button_style(palette))

    def event(self, event):
        if event.type() in _PALETTE_EVENTS:
            QtCore.QTimer.singleShot(0, self._restyle)

        return super().event(event)

    # ------------------------------------------------------------------ #
    # Painting and clicks                                                 #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        palette = self.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        path = rounded_path(self.rect())
        painter.setPen(QtGui.QPen(card_border(palette), 1))
        painter.setBrush(card_fill(palette, self._hovered and not self.toast))
        painter.drawPath(path)

        severity = QtGui.QColor(SEVERITY_COLORS[self.entry.severity])
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(QtCore.QRect(0, 0, STRIPE_WIDTH, self.height()), severity)

        if self.progress is not None:
            track = with_alpha(severity, 0.18 if is_dark(palette) else 0.14)
            bottom = QtCore.QRect(
                0, self.height() - PROGRESS_HEIGHT, self.width(), PROGRESS_HEIGHT
            )
            painter.fillRect(bottom, track)
            bottom.setWidth(int(self.width() * self.progress))
            painter.fillRect(bottom, severity)

        painter.restore()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.refresh_time()

    def mouseReleaseEvent(self, event):

        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)

        if self.toast:
            self.body_clicked.emit(self.entry)

        elif self.entry.detail and (
            self.entry.monospace_detail or self._body.overflowed or self.entry.expanded
        ):
            self.expand_clicked.emit(self.entry)

        event.accept()

    def dispose(self):
        """Stop following the entry."""
        self._binding.entry = None
