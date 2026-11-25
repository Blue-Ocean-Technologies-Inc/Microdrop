# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's contents: under the fixed header, one scroll area of
sections, each at its natural height, none scrolling by itself.

The header of the section passing under the top of the scroll area stays
pinned there, pushed up by the next section's header as it arrives, and
still collapses its section when clicked. It is a copy, laid over the
viewport and moved on every scroll: the real header scrolls on beneath.

The drawer builds DrawerContents directly (``follow_model_sections()``);
the TraitsUI view is for running it standalone against just a model::

    NotificationsPaneModel(sections=[...]).configure_traits(view=DrawerContentsView)
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, observe
from traitsui.api import BasicEditorFactory, UItem, View
from traitsui.qt.editor import Editor

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR
from microdrop_style.palette_helpers import with_alpha

# Local imports.
from ..consts import ATTENTION_SECTION_ID, HISTORY_SECTION_ID
from ..models.notifications_pane_model import NotificationsPaneModel
from .column_section import ColumnSection, card_column_of
from .drawer_header import DrawerHeader
from .section_header import HEADER_HEIGHT, SectionHeader
from .view_consts import (
    HIGHLIGHT_MS,
    LOAD_AHEAD_PX,
    REVEAL_SCROLL_MS,
    SECTION_ANIMATION_MS,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Object name of the sections' area, behind which the drawer is translucent.
SECTIONS_OBJECT_NAME = "notifications.sections"

#: Room (px) left above a revealed item, under the pinned header.
REVEAL_MARGIN = 10

#: Corner radius (px) of a highlighted item.
HIGHLIGHT_RADIUS = 8

#: Milliseconds after asking to reveal before scrolling: the layout settles.
REVEAL_DELAY_MS = 60


class _Highlight(QtWidgets.QWidget):
    """A tint laid over a revealed item, fading: "this is the one"."""

    def __init__(self, parent):
        super().__init__(parent)

        self.strength = 0.0
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._fade = QtCore.QVariantAnimation(self)
        self._fade.setDuration(HIGHLIGHT_MS)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QtCore.QEasingCurve.Type.InQuad)
        self._fade.valueChanged.connect(self._set_strength)
        self._fade.finished.connect(self.hide)

    def flash(self, rect):
        """Tint ``rect`` (in the parent's coordinates), fading out."""
        self.setGeometry(rect)
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.start()

    def _set_strength(self, value):
        self.strength = value
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(INFO_COLOR, 0.3 * self.strength))
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()), HIGHLIGHT_RADIUS, HIGHLIGHT_RADIUS
        )


class _ContentsBinding(HasTraits):
    """Hands the model's sections and reveal requests to the contents."""

    model = Instance(NotificationsPaneModel)

    view = Any()

    #: Whether the contents list the model's sections themselves, rather
    #: than a TraitsUI editor listing them.
    follow_sections = Bool(False)

    @observe("model:reveal")
    def _reveal(self, event):
        self.view.reveal(event.new)

    @observe("model:ordered_sections")
    def _show_sections(self, event):

        if self.follow_sections:
            self.view.set_sections(self.model.ordered_sections)


class DrawerContents(QtWidgets.QWidget):
    """The fixed header over one scrolling column of sections.
    ``height_changed`` follows the column's laid-out height, once per GUI
    turn: paint-only changes (hover, countdowns) never fire it."""

    height_changed = QtCore.Signal()

    def __init__(self, model, parent=None):
        super().__init__(parent)

        self.model = model
        self._sections = []
        self._height_queued = False

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
        self.column.installEventFilter(self)

        self.pinned = SectionHeader(self.scroll.viewport())
        self.pinned.pinned = True
        self.pinned.clicked.connect(self._toggle_pinned)
        self.pinned.hide()

        self._highlight = _Highlight(self.column)
        self._highlight.hide()

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

    def follow_model_sections(self):
        """List the model's sections from now on, and as they change: the
        drawer does so, with no TraitsUI UI around the contents."""
        self._binding.follow_sections = True
        self.set_sections(self.model.ordered_sections)

    def needed_width(self):
        """The least width (px) the contents need: the header's."""
        return self.header.needed_width()

    def natural_height(self):
        """The drawer height (px) showing the whole column unscrolled."""
        layout = self._column_layout
        width = self.column.width()

        if layout.hasHeightForWidth():
            column = layout.totalHeightForWidth(width)

        else:
            column = layout.totalSizeHint().height()

        return self.height() - self.scroll.viewport().height() + column

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

    def dispose(self):
        self._binding.model = None
        self.header.dispose()
        self._dispose_sections()

    # ------------------------------------------------------------------ #
    # Collapsing                                                          #
    # ------------------------------------------------------------------ #

    def _toggle(self, view):
        """Collapse or expand ``view``'s section, first scrolling its header
        to the top if it was partly scrolled away, so the header stays under
        the pointer."""
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
        above = [view for view in visible if view.y() < top]
        current = above[-1] if above else None

        if current is None or current.y() + current.height() <= top:
            self._pinned_section = None
            self.pinned.hide()

            return

        following = visible[visible.index(current) + 1 :]
        offset = min(0, following[0].y() - top - HEADER_HEIGHT) if following else 0

        self._pinned_section = current
        self.pinned.show_section(current.section, current.section.expanded, False)
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
            column = card_column_of(view)

            if view.section.expanded and column is not None and column.has_more():
                QtCore.QTimer.singleShot(0, column.load_more)

    # ------------------------------------------------------------------ #
    # Revealing an entry                                                  #
    # ------------------------------------------------------------------ #

    def reveal(self, entry):
        """Scroll to ``entry``'s card (or its section's alert widget),
        opening its section, and highlight it."""

        if entry.section_id:
            section_id = entry.section_id

        elif entry.needs_attention:
            section_id = ATTENTION_SECTION_ID

        else:
            section_id = HISTORY_SECTION_ID

        view = next((v for v in self._sections if v.section.id == section_id), None)

        if view is None:
            return

        delay = REVEAL_DELAY_MS

        if not view.section.expanded:
            view.section.expanded = True
            delay += SECTION_ANIMATION_MS

        column = card_column_of(view)

        if column is not None:
            target = column.card_for(entry)

        else:
            target = view.section.alert_widget(view.contents, entry.alert)

        if target is not None:
            QtCore.QTimer.singleShot(delay, lambda: self._scroll_to(target))

    def _scroll_to(self, target):

        try:
            self._column_layout.activate()
            top_left = target.mapTo(self.column, QtCore.QPoint(0, 0))

        # The target went with a re-list meanwhile.
        except RuntimeError:
            return

        bar = self.scroll.verticalScrollBar()
        goal = min(max(top_left.y() - HEADER_HEIGHT - REVEAL_MARGIN, 0), bar.maximum())

        self._reveal_scroll.stop()
        self._reveal_scroll.setStartValue(bar.value())
        self._reveal_scroll.setEndValue(goal)
        self._reveal_scroll.start()
        self._highlight.flash(QtCore.QRect(top_left, target.size()))

    # ------------------------------------------------------------------ #
    # Teardown and events                                                 #
    # ------------------------------------------------------------------ #

    def _dispose_sections(self):

        for view in self._sections:
            view.dispose()
            view.hide()
            view.deleteLater()

        self._sections = []

    def resizeEvent(self, event):
        super().resizeEvent(event)

        QtCore.QTimer.singleShot(0, self._place_pinned)

    def eventFilter(self, watched, event):
        event_type = event.type()

        if watched is self.column:
            if event_type == QtCore.QEvent.Type.LayoutRequest:
                self._queue_height_changed()

            return False

        if event_type == QtCore.QEvent.Type.Resize:
            self.column.setFixedWidth(watched.width())
            QtCore.QTimer.singleShot(0, self._place_pinned)

        return False

    def _queue_height_changed(self):

        if not self._height_queued:
            self._height_queued = True
            QtCore.QTimer.singleShot(0, self._announce_height)

    def _announce_height(self):
        self._height_queued = False
        self.height_changed.emit()


class _DrawerContentsEditor(Editor):
    """Shows the pane model's ordered sections as DrawerContents."""

    def init(self, parent):
        self.control = DrawerContents(self.object)

    def update_editor(self):
        self.control.set_sections(list(self.value))

    def dispose(self):

        # At app exit the window may already have deleted the contents.
        try:
            self.control.dispose()

        except RuntimeError as error:
            logger.debug(f"Drawer contents already deleted: {error}")

        super().dispose()


class DrawerContentsEditor(BasicEditorFactory):
    """Edit a list of NotificationSections as one scrolling column."""

    klass = _DrawerContentsEditor


DrawerContentsView = View(
    UItem("ordered_sections", editor=DrawerContentsEditor()),
    resizable=True,
    width=400,
    height=720,
    title="Notifications",
)
