# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""One News sub-section (a feed group): its header, its newest post (or
all of them), and "Show N more"; folding open and closed. Which groups are
collapsed or show everything is kept on the section model."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop style imports.
from microdrop_style.panel_theme import link_button_style, link_color, readable_text
from microdrop_style.typography import BUTTON, role_font

# Local imports.
from .card_style import accent_color
from .feed_parts import FeedGroupHeader, PostFrame

#: A sub-section's posts before its "Show N more".
FEED_GROUP_PREVIEW = 1

#: The largest widget height Qt allows.
_UNBOUNDED = 16_777_215

#: Indent (px) of a sub-section's posts under its header.
SUB_BODY_INDENT = 4

#: Duration (ms) of a sub-section opening or closing.
FOLD_MS = 180


class FeedSubsection(QtWidgets.QWidget):
    """One group: its header, its newest post (or all), "Show N more"."""

    def __init__(self, group, column, parent=None):
        super().__init__(parent)

        self.group = group
        self.column = column
        self._frames = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = FeedGroupHeader(group, self)
        self.header.clicked.connect(self._toggle)
        layout.addWidget(self.header)

        self.body = QtWidgets.QWidget(self)
        self._cards = QtWidgets.QVBoxLayout(self.body)
        self._cards.setContentsMargins(SUB_BODY_INDENT, 2, 0, 6)
        self._cards.setSpacing(8)
        layout.addWidget(self.body)

        self._more = QtWidgets.QPushButton(self.body)
        self._more.setFont(role_font(BUTTON))
        self._more.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._more.clicked.connect(self._toggle_more)

        self._fold = QtCore.QPropertyAnimation(self.body, b"maximumHeight", self)
        self._fold.setDuration(FOLD_MS)
        self._fold.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._fold.finished.connect(self._fold_finished)

        self.show_cards()
        self.body.setVisible(self.expanded)

    @property
    def section(self):
        return self.column.section

    @property
    def expanded(self):
        return self.group.spec.id not in self.section.collapsed_groups

    @property
    def shows_all(self):
        return self.group.spec.id in self.section.expanded_groups

    # ------------------------------------------------------------------ #
    # Cards                                                               #
    # ------------------------------------------------------------------ #

    def show_cards(self):
        """The newest post, or all of them, then "Show N more"."""
        self._dispose_frames()
        posts = self.group.posts
        shown = posts if self.shows_all else posts[:FEED_GROUP_PREVIEW]
        # The kicker's colour: the accent, readable on a card.
        accent = readable_text(
            accent_color(self.group.spec, self.palette()), self.palette(), on_card=True
        ).name()

        for index, post in enumerate(shown):
            frame = PostFrame(
                post, self.column.controller, index == 0, accent, self.body
            )
            self._cards.addWidget(frame)
            self._frames.append(frame)

        hidden = len(posts) - len(shown)
        self._more.setVisible(
            bool(hidden) or (self.shows_all and len(posts) > FEED_GROUP_PREVIEW)
        )
        self._more.setText("Show less" if self.shows_all else f"Show {hidden} more")
        self._more.setStyleSheet(
            link_button_style(self.palette(), link_color(self.palette()))
        )
        self._cards.removeWidget(self._more)
        self._cards.addWidget(self._more, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.show_new()

    def show_new(self):
        """The "new" dots, and the header's count chip."""
        new_ids = set(self.column.new_ids())
        total = len(self.group.posts)
        new = sum(post.id in new_ids for post in self.group.posts)

        for frame in self._frames:
            frame.set_new(frame.post.id in new_ids)

        summary = f"{new} new · {total}" if new else str(total)
        self.header.show_state(summary, self.expanded)

    def frame_for(self, post_id):
        """The frame of the post with ``post_id``, opening the sub-section
        and its "Show N more" if need be; None if not in this group."""
        ids = [post.id for post in self.group.posts]

        if post_id not in ids:
            return None

        if not self.expanded:
            self.section.collapsed_groups = self.section.collapsed_groups - {
                self.group.spec.id
            }
            self._show_expanded(animate=False)

        if ids.index(post_id) >= FEED_GROUP_PREVIEW and not self.shows_all:
            self.section.expanded_groups = self.section.expanded_groups | {
                self.group.spec.id
            }
            self.show_cards()

        return next((frame for frame in self._frames if frame.post.id == post_id), None)

    def _toggle_more(self):
        spec_id = self.group.spec.id

        if self.shows_all:
            self.section.expanded_groups = self.section.expanded_groups - {spec_id}

        else:
            self.section.expanded_groups = self.section.expanded_groups | {spec_id}

        self.show_cards()

    # ------------------------------------------------------------------ #
    # Folding                                                             #
    # ------------------------------------------------------------------ #

    def _toggle(self):
        spec_id = self.group.spec.id

        if self.expanded:
            self.section.collapsed_groups = self.section.collapsed_groups | {spec_id}

        else:
            self.section.collapsed_groups = self.section.collapsed_groups - {spec_id}

        self._show_expanded(animate=True)

    def _show_expanded(self, animate):
        expanded = self.expanded

        self.show_new()
        self._fold.stop()

        if not animate or not self.isVisible():
            self.body.setMaximumHeight(_UNBOUNDED)
            self.body.setVisible(expanded)

            return

        natural = self.body.sizeHint().height()

        if expanded:
            self.body.setMaximumHeight(0)
            self.body.show()
            self._fold.setStartValue(0)
            self._fold.setEndValue(natural)

        else:
            self._fold.setStartValue(self.body.height())
            self._fold.setEndValue(0)

        self._fold.start()

    def _fold_finished(self):
        self.body.setVisible(self.expanded)
        self.body.setMaximumHeight(_UNBOUNDED)

    def _dispose_frames(self):

        for frame in self._frames:
            frame.dispose()
            frame.hide()
            frame.deleteLater()

        self._frames = []

    def dispose(self):
        self._dispose_frames()
