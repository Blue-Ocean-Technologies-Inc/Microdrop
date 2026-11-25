# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""A News sub-section's parts: its header (glyph or MicroDrop's mark, title
in the text colour, count chip, detail, chevron, a short rule in the group's
accent) and a post's frame (the post's card with the "new" marker).

``make_post_card`` builds a post's card exactly as the drawer shows it.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_CHEVRON_RIGHT, ICON_EXPAND_MORE
from microdrop_style.icons.logos import MICRODROP_MARK
from microdrop_style.palette_helpers import (
    css,
    icon_font,
    scaled_logo,
    style_chip,
    tinted,
    with_alpha,
)
from microdrop_style.panel_theme import chip_text, chip_tint, link_color, muted_text
from microdrop_style.typography import (
    BODY_TEXT,
    BUTTON,
    CARD_TITLE,
    CHIP,
    META,
    SUBSECTION_TITLE,
    role_font,
)

# Microdrop utils imports.
from microdrop_utils.clamped_label import ElidedLabel
from microdrop_utils.new_marker import NEW_DOT_SIZE, NewDot

# Local imports.
from ..consts import RELEASES_GROUP_ID
from ..models.feed_groups import SUBTITLE_LATEST
from ..models.feed_model import format_post_date
from .card_style import GRID, accent_color
from .post_card import FeedPostCard
from .status_banner import HEADER_RULE_SIZE


def make_post_card(post, controller, lead, accent, palette):
    """A post's card as the drawer shows it: the drawer's type roles and
    link colour, ``accent`` on its kicker. Call ``create(parent)`` on it."""
    return FeedPostCard(
        post=post,
        controller=controller,
        lead=lead,
        accent=accent,
        link_color=link_color(palette).name(),
        fonts={
            "title": role_font(CARD_TITLE),
            "small": role_font(META),
            "body": role_font(BODY_TEXT),
            "link": role_font(BUTTON),
        },
    )


#: Pixel size of a sub-section header's glyph or mark, beside its title.
SUBSECTION_GLYPH_SIZE = 18

#: The group whose header names its newest post's date (MicroDrop's
#: release notes, RELEASES_GROUP_ID, show MicroDrop's mark).
NEWSLETTERS_GROUP_ID = "newsletters"


def group_detail(group):
    """The right-aligned detail of a group's header: the latest release
    ("latest v1.48.0", as the feed's own header says it), the newest
    newsletter's date, or nothing."""

    if group.spec.subtitle == SUBTITLE_LATEST:
        return group.subtitle

    if group.spec.id == NEWSLETTERS_GROUP_ID and group.posts:
        return format_post_date(group.posts[0])

    return ""


class FeedGroupHeader(QtWidgets.QWidget):
    """A feed group's header on one row: glyph, large bold title in the
    group's colour, its count chip, the detail muted and elided to the room
    left, the chevron at the far right; a short rule under the title. A
    click emits ``clicked``."""

    clicked = QtCore.Signal()

    def __init__(self, group, parent=None):
        super().__init__(parent)

        self.group = group
        accent = accent_color(group.spec, self.palette()).name()

        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)

        # One row, and the rule under the title's column.
        header = QtWidgets.QGridLayout(self)
        header.setContentsMargins(4, GRID, 4, GRID // 2)
        header.setHorizontalSpacing(GRID)
        header.setVerticalSpacing(GRID // 2)
        header.setColumnStretch(3, 1)

        # MicroDrop's releases carry its mark, in the group's colour.
        glyph = QtWidgets.QLabel(group.spec.glyph, self)

        if group.spec.id == RELEASES_GROUP_ID:
            mark = scaled_logo(
                MICRODROP_MARK, SUBSECTION_GLYPH_SIZE, self.devicePixelRatioF()
            )
            glyph.setPixmap(tinted(mark, accent))

        else:
            glyph.setFont(icon_font(SUBSECTION_GLYPH_SIZE))
            glyph.setStyleSheet(f"QLabel {{ color: {accent}; }}")

        header.addWidget(glyph, 0, 0)

        title = ElidedLabel(group.spec.title, self, title=True)
        title.setFont(role_font(SUBSECTION_TITLE))
        header.addWidget(title, 0, 1)

        self._chip = QtWidgets.QLabel(self)
        self._chip.setFont(role_font(CHIP))
        style_chip(
            self._chip,
            f"color: {css(chip_text(accent, self.palette()))};"
            f" background: {css(with_alpha(accent, chip_tint(self.palette())))};",
        )
        header.addWidget(self._chip, 0, 2)

        detail = ElidedLabel(group_detail(group), self)
        detail.setForegroundRole(QtGui.QPalette.ColorRole.PlaceholderText)
        detail.setFont(role_font(META))
        header.addWidget(detail, 0, 3)

        self._chevron = QtWidgets.QLabel(self)
        self._chevron.setFont(icon_font(20))
        self._chevron.setStyleSheet(
            f"QLabel {{ color: {muted_text(self.palette()).name()}; }}"
        )
        header.addWidget(self._chevron, 0, 4)

        rule = QtWidgets.QFrame(self)
        rule.setFixedSize(*HEADER_RULE_SIZE)
        rule.setStyleSheet(f"QFrame {{ background: {accent}; border-radius: 1px; }}")
        header.addWidget(rule, 1, 1, QtCore.Qt.AlignmentFlag.AlignLeft)

    def show_state(self, summary, expanded):
        """Show ``summary`` in the chip, the chevron for ``expanded``."""
        self._chip.setText(summary)
        self._chip.setVisible(bool(summary))
        self._chevron.setText(ICON_EXPAND_MORE if expanded else ICON_CHEVRON_RIGHT)
        self.setToolTip(
            f"{'Collapse' if expanded else 'Expand'} {self.group.spec.title}"
        )

    def paintEvent(self, event):

        if not self.underMouse():
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        text = self.palette().color(QtGui.QPalette.ColorRole.Text)
        painter.setBrush(with_alpha(text, 0.05))
        painter.drawRoundedRect(QtCore.QRectF(self.rect()), 7, 7)

    def mouseReleaseEvent(self, event):

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()

        event.accept()


class PostFrame(QtWidgets.QWidget):
    """A feed post's card with the "new" dot and the highlight over it."""

    def __init__(self, post, controller, lead, accent, parent=None):
        super().__init__(parent)

        self.post = post

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.card = make_post_card(post, controller, lead, accent, self.palette())
        layout.addWidget(self.card.create(self))

        self._dot = NewDot(self)
        self._dot.hide()

    def set_new(self, new):
        self._dot.setVisible(new)
        self._dot.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._dot.move(self.width() - NEW_DOT_SIZE - 12, 8)
        self._dot.raise_()

    def dispose(self):
        self.card.dispose()
