# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's one-column layout: under the fixed header, one scroll area
of sections, each at its natural height, none scrolling by itself.

The header of the section passing under the top of the scroll area stays
pinned there, pushed up by the next section's header as it arrives, and
still collapses its section when clicked. It is a copy, laid over the
viewport and moved on every scroll: the real header scrolls on beneath.

Runs standalone against just a model::

    UxPaneModel(sections=[...]).configure_traits(view=ColumnDrawerView)
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, HasTraits, Instance, observe
from traits.observation.api import trait
from traitsui.api import BasicEditorFactory, UItem, View
from traitsui.qt.editor import Editor

# Microdrop package imports.
from notifications.consts import NotificationSection

# Local imports.
from .column_parts import CardColumn, fit_item_views
from .drawer_view import SECTIONS_OBJECT_NAME, DrawerHeader, _ContentsBinding
from .feed_column import FeedColumn
from .news_models import NewsSection
from .section_view import HEADER_HEIGHT, SectionHeader
from .ux_consts import (
    ATTENTION_SECTION_ID,
    DEFAULT_SECTION_STYLE,
    HISTORY_SECTION_ID,
    LOAD_AHEAD_PX,
    NEWS_SECTION_ID,
    REVEAL_SCROLL_MS,
    SECTION_ANIMATION_MS,
    SECTION_STYLES,
)
from .ux_models import CardListSection, UxPaneModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The largest widget height Qt allows.
_UNBOUNDED = 16_777_215

#: Room (px) left above a revealed card, under the pinned header.
REVEAL_MARGIN = 10


def build_section_contents(section, pane_model, parent):
    """A section's contents for the column: cards, the feed's preview, or
    the contributor's own contents grown to their natural height."""

    if isinstance(section, CardListSection):
        return CardColumn(
            pane_model,
            section.entries_name,
            activity=section.id == HISTORY_SECTION_ID,
            parent=parent,
        )

    if isinstance(section, NewsSection):
        return FeedColumn(section, pane_model, parent)

    contents = section.factory(parent)
    fit_item_views(getattr(contents, "control", contents))

    return contents


class _SectionBinding(HasTraits):
    """Shows the section model's changes in its column view."""

    section = Instance(NotificationSection)

    view = Any()

    @observe("section:[title, summary]")
    def _show_header(self, event):
        self.view.show_header()

    @observe("section:expanded")
    def _show_expanded(self, event):
        self.view.show_expanded(animate=True)

    # Only the prototype's own sections have ``available``.
    @observe(trait("section", notify=False).trait("available", optional=True))
    def _show_available(self, event):
        self.view.setVisible(event.new)
        self.view.header_changed.emit()


class ColumnSection(QtWidgets.QWidget):
    """A section's header over its contents, at their natural height."""

    #: The header was clicked.
    toggle_requested = QtCore.Signal(object)

    #: Its title, summary or state changed: a pinned copy must follow.
    header_changed = QtCore.Signal()

    def __init__(self, section, pane_model, parent=None):
        super().__init__(parent)

        self.section = section
        self.pane_model = pane_model
        self.style_ = SECTION_STYLES.get(section.id, DEFAULT_SECTION_STYLE)

        #: What was built for it: a widget, or a TraitsUI UI around one.
        self.contents = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SectionHeader(self.style_, self)
        self.header.clicked.connect(lambda: self.toggle_requested.emit(self))
        layout.addWidget(self.header)

        self.body = QtWidgets.QWidget(self)
        body_layout = QtWidgets.QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.body)

        self._fold = QtCore.QPropertyAnimation(self.body, b"maximumHeight", self)
        self._fold.setDuration(SECTION_ANIMATION_MS)
        self._fold.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._fold.finished.connect(self._fold_finished)

        self._binding = _SectionBinding(section=section, view=self)
        self.setVisible(getattr(section, "available", True))
        self.show_header()
        self.show_expanded(animate=False)

    @property
    def contents_widget(self):
        return getattr(self.contents, "control", self.contents)

    def show_header(self):
        section = self.section

        self.header.show_section(section.title, section.summary, section.expanded, True)
        self.header_changed.emit()

    def show_expanded(self, animate):
        expanded = self.section.expanded

        if expanded and self.contents is None:
            self._build_contents()

        self.header.show_section(
            self.section.title, self.section.summary, expanded, animate
        )
        self.header_changed.emit()
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
        self.body.setVisible(self.section.expanded)
        self.body.setMaximumHeight(_UNBOUNDED)

    def _build_contents(self):
        """Build the contents; a failure shows in place of them."""

        try:
            self.contents = build_section_contents(
                self.section, self.pane_model, self.body
            )

        except Exception as error:
            logger.exception(f"Notification section {self.section.id} failed")
            self.contents = QtWidgets.QLabel(f"Could not show this: {error}")

        self.body.layout().addWidget(self.contents_widget)

    def dispose(self):
        self._binding.section = None
        dispose = getattr(self.contents, "dispose", None)

        if dispose is not None:
            dispose()

        self.contents = None


class _RevealBinding(HasTraits):
    """Hands the model's reveal requests to the column."""

    model = Instance(UxPaneModel)

    view = Any()

    @observe("model:reveal")
    def _reveal(self, event):
        self.view.reveal(event.new)


class ColumnDrawerContents(QtWidgets.QWidget):
    """The fixed header over one scrolling column of sections."""

    def __init__(self, model, parent=None):
        super().__init__(parent)

        self.model = model
        self._sections = []

        #: The section whose header is pinned, if any.
        self._pinned_section = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = DrawerHeader(model, self)
        layout.addWidget(self.header)

        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setObjectName(SECTIONS_OBJECT_NAME)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.scroll.viewport().setAutoFillBackground(False)
        layout.addWidget(self.scroll, 1)

        self.column = QtWidgets.QWidget()
        self.column.setAutoFillBackground(False)
        self._column_layout = QtWidgets.QVBoxLayout(self.column)
        self._column_layout.setContentsMargins(0, 6, 0, 16)
        self._column_layout.setSpacing(2)
        self._column_layout.addStretch(1)
        self.scroll.setWidget(self.column)

        self.pinned = SectionHeader(DEFAULT_SECTION_STYLE, self.scroll.viewport())
        self.pinned.pinned = True
        self.pinned.clicked.connect(self._toggle_pinned)
        self.pinned.hide()

        self._reveal_scroll = QtCore.QPropertyAnimation(
            self.scroll.verticalScrollBar(), b"value", self
        )
        self._reveal_scroll.setDuration(REVEAL_SCROLL_MS)
        self._reveal_scroll.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)

        # The column is exactly as wide as the viewport: a wide child must
        # wrap or cut, never push the cards past the drawer's edge.
        self.scroll.viewport().installEventFilter(self)

        bar = self.scroll.verticalScrollBar()
        bar.valueChanged.connect(self._follow_scroll)
        bar.rangeChanged.connect(self._follow_scroll)

        self._binding = _ContentsBinding(model=model, view=self)
        self._reveal_binding = _RevealBinding(model=model, view=self)
        self.show_counts()

    def show_counts(self):
        center = self.model.center

        self.header.show_counts(
            len(center.entries), center.new_count, len(center.attention_entries)
        )

    def set_sections(self, sections):
        """Show ``sections``, top first."""
        self._dispose_sections()

        for position, section in enumerate(sections):
            view = ColumnSection(section, self.model, self.column)
            view.toggle_requested.connect(self._toggle)
            view.header_changed.connect(self._follow_scroll)
            self._column_layout.insertWidget(position, view)
            self._sections.append(view)

        self._follow_scroll()

    # ------------------------------------------------------------------ #
    # Collapsing                                                          #
    # ------------------------------------------------------------------ #

    def _toggle(self, view):
        """Collapse or expand ``view``'s section, first scrolling its header
        to the top if it was partly scrolled away, so the header stays
        under the pointer."""
        bar = self.scroll.verticalScrollBar()

        if view.y() < bar.value():
            self._reveal_scroll.stop()
            bar.setValue(view.y())

        view.section.expanded = not view.section.expanded

    def _toggle_pinned(self):

        if self._pinned_section is not None:
            self._toggle(self._pinned_section)

    # ------------------------------------------------------------------ #
    # The pinned header, and loading as the scroll nears the end         #
    # ------------------------------------------------------------------ #

    def _follow_scroll(self, *args):
        self._place_pinned()
        self._load_ahead()

    def _place_pinned(self):
        """Pin a copy of the header of the section under the top edge; the
        next section's header pushes it up."""
        top = self.scroll.verticalScrollBar().value()
        visible = [view for view in self._sections if view.isVisible()]
        current = None

        for view in visible:
            if view.y() < top:
                current = view

        if current is None or current.y() + current.height() <= top:
            self._pinned_section = None
            self.pinned.hide()

            return

        following = visible[visible.index(current) + 1 :]
        offset = 0

        if following:
            offset = min(0, following[0].y() - top - HEADER_HEIGHT)

        section = current.section
        self._pinned_section = current
        self.pinned.style_ = current.style_
        self.pinned.show_section(
            section.title, section.summary, section.expanded, False
        )
        self.pinned.setGeometry(
            0, offset, self.scroll.viewport().width(), HEADER_HEIGHT
        )
        self.pinned.show()
        self.pinned.raise_()

    def _load_ahead(self):
        """Build Activity's next cards once the scroll nears the end."""
        bar = self.scroll.verticalScrollBar()

        if bar.maximum() - bar.value() > LOAD_AHEAD_PX:
            return

        for view in self._sections:
            column = view.contents_widget

            if view.section.id == HISTORY_SECTION_ID and view.section.expanded:
                if isinstance(column, CardColumn) and column.has_more():
                    QtCore.QTimer.singleShot(0, column.load_more)

    # ------------------------------------------------------------------ #
    # Revealing a card                                                    #
    # ------------------------------------------------------------------ #

    def reveal(self, entry):
        """Scroll to ``entry``'s card, opening its section, and highlight
        it."""
        if entry.feed_post_id:
            section_id = NEWS_SECTION_ID

        elif entry.needs_attention:
            section_id = ATTENTION_SECTION_ID

        else:
            section_id = HISTORY_SECTION_ID

        view = next(
            (view for view in self._sections if view.section.id == section_id), None
        )

        if view is None:
            return

        delay = 60

        if not view.section.expanded:
            view.section.expanded = True
            delay += SECTION_ANIMATION_MS

        column = view.contents_widget

        if isinstance(column, FeedColumn):
            card = column.frame_for(entry.feed_post_id)

        elif isinstance(column, CardColumn):
            card = column.card_for(entry)

        else:
            return

        if card is not None:
            QtCore.QTimer.singleShot(delay, lambda: self._scroll_to(card))

    def _scroll_to(self, card):
        try:
            self._column_layout.activate()
            y = card.mapTo(self.column, QtCore.QPoint(0, 0)).y()

        # The card went with a re-list meanwhile.
        except RuntimeError:
            return

        bar = self.scroll.verticalScrollBar()
        target = min(max(y - HEADER_HEIGHT - REVEAL_MARGIN, 0), bar.maximum())

        self._reveal_scroll.stop()
        self._reveal_scroll.setStartValue(bar.value())
        self._reveal_scroll.setEndValue(target)
        self._reveal_scroll.start()
        card.flash()

    # ------------------------------------------------------------------ #
    # Teardown                                                            #
    # ------------------------------------------------------------------ #

    def _dispose_sections(self):

        for view in self._sections:
            view.dispose()
            view.hide()
            view.deleteLater()

        self._sections = []

    def dispose(self):
        self._binding.model = None
        self._reveal_binding.model = None
        self._dispose_sections()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        QtCore.QTimer.singleShot(0, self._place_pinned)

    def eventFilter(self, watched, event):

        if event.type() == QtCore.QEvent.Type.Resize:
            self.column.setFixedWidth(watched.width())
            QtCore.QTimer.singleShot(0, self._place_pinned)

        return False


class _ColumnContentsEditor(Editor):
    """Shows the pane model's ordered sections as ColumnDrawerContents."""

    def init(self, parent):
        self.control = ColumnDrawerContents(self.object)

    def update_editor(self):
        self.control.set_sections(list(self.value))

    def dispose(self):
        # At app exit the window may already have deleted the contents.
        try:
            self.control.dispose()

        except RuntimeError:
            pass

        super().dispose()


class ColumnContentsEditor(BasicEditorFactory):
    """Edit a list of NotificationSections as one scrolling column."""

    klass = _ColumnContentsEditor


ColumnDrawerView = View(
    UItem("ordered_sections", editor=ColumnContentsEditor()),
    resizable=True,
    width=400,
    height=720,
    title="Notifications",
)
