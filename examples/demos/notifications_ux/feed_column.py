# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed in the drawer's one-column layout: its status line,
then one sub-section per group (Top stories, What's new in MicroDrop,
Newsletters, ...), each a header one level below the main ones that
collapses and expands, showing the group's newest post and "Show N more".

Built here from the feed model's groups with the feed's own post cards
(``FeedPostCard``); which sub-sections are collapsed or show everything is
kept on the section model, for the session.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, observe
from traitsui.api import UItem, View

# Microdrop package imports.
from examples.demos.notifications_pane.sci_bots_feed_cards import FeedPostCard
from examples.demos.notifications_pane.sci_bots_feed_view import StatusBannerEditor

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR

# Local imports.
from .card_parts import NEW_DOT_SIZE, NewDot
from .feed_models import UxFeedSection
from .section_view import SectionHeader
from .ux_consts import (
    FEED_GROUP_PREVIEW,
    HIGHLIGHT_MS,
    SECTION_ANIMATION_MS,
    SectionStyle,
)
from .ux_models import UxPaneModel
from .view_styles import link_button_style, with_alpha

#: The largest widget height Qt allows.
_UNBOUNDED = 16_777_215

#: Indent (px) of a sub-section's posts under its header.
SUB_BODY_INDENT = 12

#: Corner radius (px) of a highlighted post.
HIGHLIGHT_RADIUS = 10

#: The feed's status line ("Pushed 1 new post"), as its own view shows it.
FeedStatusView = View(
    UItem(
        "status_text",
        editor=StatusBannerEditor(error_name="status_is_error"),
        visible_when="status_text",
    ),
)


class _Highlight(QtWidgets.QWidget):
    """A tint over a post, fading: "this is the one"."""

    def __init__(self, parent):
        super().__init__(parent)

        self.strength = 0.0

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):

        if self.strength <= 0:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(INFO_COLOR, 0.3 * self.strength))
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()), HIGHLIGHT_RADIUS, HIGHLIGHT_RADIUS
        )


class PostFrame(QtWidgets.QWidget):
    """A feed post's card with the "new" dot and the highlight over it."""

    def __init__(self, post, controller, lead, accent, parent=None):
        super().__init__(parent)

        self.post = post

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.card = FeedPostCard(
            post=post, controller=controller, lead=lead, accent=accent
        )
        layout.addWidget(self.card.create(self))

        self._highlight = _Highlight(self)
        self._dot = NewDot(self)
        self._dot.hide()

        self._fade = QtCore.QVariantAnimation(self)
        self._fade.setDuration(HIGHLIGHT_MS)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QtCore.QEasingCurve.Type.InQuad)
        self._fade.valueChanged.connect(self._set_strength)

    def set_new(self, new):
        self._dot.setVisible(new)
        self._dot.raise_()

    def flash(self):
        self._fade.stop()
        self._fade.start()

    def _set_strength(self, value):
        self._highlight.strength = value
        self._highlight.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._highlight.setGeometry(self.rect())
        self._highlight.raise_()
        self._dot.move(self.width() - NEW_DOT_SIZE - 12, 8)
        self._dot.raise_()

    def dispose(self):
        self.card.dispose()


class FeedSubsection(QtWidgets.QWidget):
    """One group: its header, its newest post (or all), "Show N more"."""

    def __init__(self, group, column, parent=None):
        super().__init__(parent)

        self.group = group
        self.column = column
        self._frames = []

        spec = group.spec
        style = SectionStyle(spec.glyph, spec.accent[0], 0, False)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SectionHeader(style, self, level=1)
        self.header.clicked.connect(self._toggle)
        layout.addWidget(self.header)

        self.body = QtWidgets.QWidget(self)
        self._cards = QtWidgets.QVBoxLayout(self.body)
        self._cards.setContentsMargins(SUB_BODY_INDENT, 2, 0, 6)
        self._cards.setSpacing(8)
        layout.addWidget(self.body)

        self._more = QtWidgets.QPushButton(self.body)
        self._more.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._more.clicked.connect(self._toggle_more)

        self._fold = QtCore.QPropertyAnimation(self.body, b"maximumHeight", self)
        self._fold.setDuration(SECTION_ANIMATION_MS)
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
        accent = self.header.style_.accent

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
        self._more.setStyleSheet(link_button_style(self.palette(), INFO_COLOR))
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
        self.header.show_section(self.group.spec.title, summary, self.expanded, False)

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


class _FeedBinding(HasTraits):
    """Rebuilds the sub-sections when the feed's groups change, and the
    "new" marks when the alerts do."""

    section = Instance(UxFeedSection)

    pane_model = Instance(UxPaneModel)

    view = Any()

    @observe("section:controller:model:groups")
    def _rebuild(self, event):
        self.view.schedule_rebuild()

    @observe("pane_model:feed_alerts.items.[unread, is_new]")
    def _show_new(self, event):
        self.view.show_new()


class FeedColumn(QtWidgets.QWidget):
    """The feed's status line over its sub-sections, at natural height."""

    def __init__(self, section, pane_model, parent=None):
        super().__init__(parent)

        self.section = section
        self.pane_model = pane_model
        self.controller = section.controller
        self._subsections = []
        self._rebuild_queued = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 8, 6)
        layout.setSpacing(0)

        self._status_ui = self.controller.edit_traits(
            view=FeedStatusView, kind="subpanel", parent=self
        )
        layout.addWidget(self._status_ui.control)

        self._groups = QtWidgets.QVBoxLayout()
        self._groups.setSpacing(2)
        layout.addLayout(self._groups)

        self._binding = _FeedBinding(section=section, pane_model=pane_model, view=self)
        self.rebuild()

    def new_ids(self):
        """Ids of the posts marked new: arrived and not seen, or seen in
        the drawer open now."""
        return [
            entry.feed_post_id
            for entry in self.pane_model.feed_alerts
            if entry.unread or entry.is_new
        ]

    def schedule_rebuild(self):

        if not self._rebuild_queued:
            self._rebuild_queued = True
            QtCore.QTimer.singleShot(0, self.rebuild)

    def rebuild(self):
        """A sub-section per group; the model leaves empty groups out."""
        self._rebuild_queued = False
        self._dispose_subsections()

        for group in self.controller.model.groups:
            subsection = FeedSubsection(group, self, self)
            self._groups.addWidget(subsection)
            self._subsections.append(subsection)

    def show_new(self):

        for subsection in self._subsections:
            subsection.show_new()

    def frame_for(self, post_id):
        """The frame of the post with ``post_id``, its sub-section opened."""

        if self._rebuild_queued:
            self.rebuild()

        for subsection in self._subsections:
            frame = subsection.frame_for(post_id)

            if frame is not None:
                return frame

        return None

    def _dispose_subsections(self):

        for subsection in self._subsections:
            subsection.dispose()
            subsection.hide()
            subsection.deleteLater()

        self._subsections = []

    def dispose(self):
        self._binding.section = None
        self._binding.pane_model = None
        self._dispose_subsections()
        self._status_ui.dispose()
