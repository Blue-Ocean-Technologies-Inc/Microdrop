# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Small pieces of a notification card: its meta line, its "new" marker,
its footer of buttons, and the style sheet all cards share."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR
from microdrop_style.palette_helpers import css, is_dark, rounded_path, with_alpha

# Local imports.
from . import colour_roles
from .formatting import format_time
from .theme import (
    accent_of,
    card_border,
    card_fill,
    icon_button_style,
    link_button_style,
    link_color,
    muted_text,
    outlined_button_style,
    primary_button_style,
    quiet_button_style,
    role_color,
    theme_palette,
)
from .typography import BUTTON, role_font
from .view_consts import CARD_RADIUS, DETAIL_MAX_HEIGHT

#: Width (px) of the severity stripe down a card's left edge.
STRIPE_WIDTH = 4

#: Height (px) of a toast's countdown line along the card's bottom.
PROGRESS_HEIGHT = 3

#: Diameter (px) of the "new" marker.
NEW_DOT_SIZE = 8

#: Space (px) between the footer's controls, across and between rows.
FOOTER_SPACING = 10
FOOTER_ROW_SPACING = 4

#: The cards' shared style sheet, by palette.
_STYLE_SHEETS = {}


def source_label(entry):
    """Who posted ``entry``, readable: "device_viewer.models" -> "Device
    viewer"."""
    source = entry.source or entry.category
    head = source.split(".")[0].replace("_", " ").strip()

    return head[:1].upper() + head[1:]


def meta_text(entry):
    """The line under the title: "Source · 3 min ago · ×2"."""
    parts = [source_label(entry), format_time(entry.last_seen)]

    if entry.count > 1:
        parts.append(f"×{entry.count}")

    return " · ".join(part for part in parts if part)


def palette_key(palette):
    """What a palette's derived styles depend on."""
    return (
        palette.color(QtGui.QPalette.ColorRole.Window).rgba(),
        palette.color(QtGui.QPalette.ColorRole.Text).rgba(),
    )


def card_style_sheet(palette):
    """The style sheet every card shares in ``palette``, its parts picked by
    object name; made once per theme. One sheet per card rather than one
    per part: a sheet per part made building a card several times slower."""
    key = palette_key(palette)
    sheet = _STYLE_SHEETS.get(key)

    if sheet is not None:
        return sheet

    text = palette.color(QtGui.QPalette.ColorRole.Text)
    muted = muted_text(palette)
    glyphs = " ".join(
        f"QLabel#cardGlyph_{severity} {{ color: {css(role_color(palette, pair))}; }}"
        for severity, pair in colour_roles.SEVERITY.items()
    )
    sheet = " ".join(
        [
            f"QLabel#cardMeta, QLabel#cardActed {{ color: {css(muted)}; }}",
            f"QLabel#cardBody {{ color: {css(text)}; }}",
            glyphs,
            icon_button_style(palette, 16, "QToolButton#cardDismiss"),
            link_button_style(palette, link_color(palette), "QPushButton#cardMore"),
            link_button_style(palette, link_color(palette), "QPushButton#cardHelp"),
            outlined_button_style(palette, "QPushButton#cardHelpOnly"),
            quiet_button_style(palette, "QPushButton#cardLater"),
            primary_button_style(palette, "QPushButton#cardPrimary"),
            "QPlainTextEdit#cardTraceback {"
            f" background: {css(with_alpha(text, 0.05))};"
            " border: none; border-radius: 4px; }",
        ]
    )
    _STYLE_SHEETS[key] = sheet

    return sheet


def stripe_color(entry, palette):
    """The stripe's colour: the entry's own accent, else its severity's."""

    if entry.accent:
        return accent_of(entry.accent, palette)

    return role_color(palette, colour_roles.SEVERITY[entry.severity])


def restyle_by_name(widget, name):
    """Give ``widget`` object name ``name`` and re-apply the style sheet's
    rules picked by it."""

    if widget.objectName() != name:
        widget.setObjectName(name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def paint_card(painter, rect, palette, stripe, hovered, flash, progress):
    """Paint a card's rounded surface in ``rect``: its border, its fill
    (lighter while ``hovered``), a fading highlight of strength ``flash``,
    the ``stripe`` down its left edge, and a toast's countdown at
    ``progress`` (0-1, or None for none)."""
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    path = rounded_path(rect, CARD_RADIUS)
    painter.setPen(QtGui.QPen(card_border(palette), 1))
    painter.setBrush(card_fill(palette, hovered))
    painter.drawPath(path)

    if flash > 0:
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(INFO_COLOR, 0.3 * flash))
        painter.drawPath(path)

    painter.setClipPath(path)
    painter.fillRect(QtCore.QRect(0, 0, STRIPE_WIDTH, rect.height()), stripe)

    if progress is not None:
        track = with_alpha(stripe, 0.18 if is_dark(palette) else 0.14)
        bottom = QtCore.QRect(
            0, rect.height() - PROGRESS_HEIGHT, rect.width(), PROGRESS_HEIGHT
        )
        painter.fillRect(bottom, track)
        bottom.setWidth(int(rect.width() * progress))
        painter.fillRect(bottom, stripe)

    painter.end()


class TracebackView(QtWidgets.QPlainTextEdit):
    """An expanded traceback: monospace, unwrapped, as tall as its lines up
    to DETAIL_MAX_HEIGHT."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("cardTraceback")
        self.setReadOnly(True)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(
            QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        )

    def show_detail(self, detail):
        """Show ``detail``, sized to it."""

        if self.toPlainText() != detail:
            self.setPlainText(detail)

        lines = len(detail.splitlines()) + 1
        line_height = QtGui.QFontMetrics(self.font()).lineSpacing()

        self.setFixedHeight(min(lines * line_height + 24, DETAIL_MAX_HEIGHT))
        self.show()


class NewDot(QtWidgets.QWidget):
    """The "new" marker: a small filled circle in the strong text colour."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(NEW_DOT_SIZE + 4, NEW_DOT_SIZE + 4)
        self.setToolTip("New since you last opened notifications")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(theme_palette().color(QtGui.QPalette.ColorRole.Text))
        painter.drawEllipse(QtCore.QRectF(2, 2, NEW_DOT_SIZE, NEW_DOT_SIZE))


class CardFooter(QtWidgets.QWidget):
    """A card's buttons and its "Show more" link, on one row while they fit;
    narrower, "Show more" takes a row of its own beneath, then the second
    button joins it. Labels are never cut."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.primary = self._button("cardPrimary")
        self.secondary = self._button("")
        self.more = self._button("cardMore")
        self._arrangement = None

        # Its width is the card's to give: the rows follow it.
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred
        )

        rows = QtWidgets.QVBoxLayout(self)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(FOOTER_ROW_SPACING)

        self._rows = [QtWidgets.QHBoxLayout(), QtWidgets.QHBoxLayout()]

        for row in self._rows:
            row.setSpacing(FOOTER_SPACING)
            rows.addLayout(row)

    def _button(self, name):
        button = QtWidgets.QPushButton(self)
        button.setObjectName(name)
        button.setFont(role_font(BUTTON))
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed
        )
        button.hide()

        return button

    def arrange(self):
        """Lay the shown controls out for the footer's width."""
        buttons = [b for b in (self.primary, self.secondary) if not b.isHidden()]
        more = [] if self.more.isHidden() else [self.more]

        if self._fits(buttons + more):
            rows = (buttons + more, [])

        elif self._fits(buttons):
            rows = (buttons, more)

        else:
            rows = (buttons[:1], buttons[1:] + more)

        arrangement = tuple(tuple(id(control) for control in row) for row in rows)

        if arrangement == self._arrangement:
            return

        self._arrangement = arrangement

        for layout, controls in zip(self._rows, rows):
            while layout.count():
                layout.takeAt(0)

            for control in controls:
                if control is not self.more:
                    layout.addWidget(control)

            # "Show more" sits at the far end of its row.
            layout.addStretch(1)

            if self.more in controls:
                layout.addWidget(self.more)

    def _fits(self, controls):
        width = sum(control.sizeHint().width() for control in controls)

        return width + FOOTER_SPACING * max(len(controls) - 1, 0) <= self.width()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.arrange()
