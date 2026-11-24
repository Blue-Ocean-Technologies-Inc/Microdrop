# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed: a status banner, then the posts under colour-coded
group headers, each group's first post a lead card and the rest compact
rows, with "Show all" past the first few.

The view only renders the model's groups; clicks go to the controller, the
edit_traits handler. Everything is painted from the palette and rebuilt
when it changes, so the feed follows a live theme switch. Runs standalone
against the model alone (clicks then do nothing) or with the controller::

    controller = SciBotsFeedController(
        sources=[JsonFileFeedSource(path=str(DEFAULT_FEED_PATH))]
    )
    controller.reload()
    controller.configure_traits(view=SciBotsFeedView)
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, List, Str, observe
from traitsui.api import BasicEditorFactory, UItem, VGroup, View
from traitsui.qt.editor import Editor

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY

# Local imports.
from .sci_bots_feed_cards import (
    CORNER_RADIUS,
    GRID,
    SMALL_POINTS,
    FeedPostCard,
    accent_color,
    scaled_font,
)
from .sci_bots_feed_model import FeedGroup

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Points added to the base font for a group header.
HEADER_POINTS = 5

#: Pixel size of a header's glyph, and the status banner's.
HEADER_GLYPH_SIZE = 22
STATUS_GLYPH_SIZE = 18

#: The short accent rule under a header.
HEADER_RULE_SIZE = (4 * GRID, 3)

#: How tall the feed would like to be, given room.
FEED_PREFERRED_HEIGHT = 560

#: The empty state's glyph and words.
EMPTY_GLYPH = "newspaper"
EMPTY_TITLE = "No news yet"
EMPTY_TEXT = "Posts from Sci-Bots and new MicroDrop releases appear here."

_ROLE = QtGui.QPalette.ColorRole
_ALIGN = QtCore.Qt.AlignmentFlag
_PALETTE_EVENTS = (
    QtCore.QEvent.Type.PaletteChange,
    QtCore.QEvent.Type.ApplicationPaletteChange,
)


def _glyph_label(glyph, pixel_size, color, parent):
    label = QtWidgets.QLabel(glyph, parent)
    font = QtGui.QFont(ICON_FONT_FAMILY)
    font.setPixelSize(pixel_size)
    label.setFont(font)
    label.setStyleSheet(f"QLabel {{ color: {color}; }}")

    return label


def _link_html(text, color):
    return (
        f'<a href="#" style="color: {color}; text-decoration: none;"><b>{text}</b></a>'
    )


class ThemedWidget(QtWidgets.QWidget):
    """Says when its palette changes."""

    palette_changed = QtCore.Signal()

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() in _PALETTE_EVENTS:
            self.palette_changed.emit()


class FeedGroupPanel(HasTraits):
    """One group: its header, its cards and its "Show all"."""

    #: The group shown.
    group = Instance(FeedGroup)

    #: The SciBotsFeedController clicks go to; None ignores them.
    controller = Any()

    #: The panel.
    control = Any()

    #: The cards on show, and the layout holding them.
    _cards = List(Instance(FeedPostCard))
    _cards_layout = Any()

    #: The "Show all (7)" link.
    _show_all = Any()

    def create(self, parent):
        """Build the panel."""
        self.control = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(self.control)
        layout.setContentsMargins(0, 2 * GRID, 0, GRID)
        layout.setSpacing(GRID)

        layout.addLayout(self._create_header())

        self._cards_layout = QtWidgets.QVBoxLayout()
        self._cards_layout.setSpacing(GRID)
        layout.addLayout(self._cards_layout)

        self._show_all = QtWidgets.QLabel(self.control)
        self._show_all.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._show_all.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._show_all.linkActivated.connect(self._toggle_show_all)
        layout.addWidget(self._show_all, 0, _ALIGN.AlignRight)

        self._show_cards()

        return self.control

    def dispose(self):
        self._dispose_cards()
        self.trait_set(group=None, controller=None)

    def _accent(self):
        return accent_color(self.group.spec, self.control.palette()).name()

    def _create_header(self):
        """Glyph and bold title in the accent, the count muted at the right,
        a short accent rule under them."""
        spec = self.group.spec
        accent = self._accent()
        header = QtWidgets.QVBoxLayout()
        header.setSpacing(GRID // 2)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(GRID)

        row.addWidget(_glyph_label(spec.glyph, HEADER_GLYPH_SIZE, accent, self.control))

        title = QtWidgets.QLabel(spec.title, self.control)
        title.setFont(scaled_font(self.control, HEADER_POINTS, bold=True))
        title.setStyleSheet(f"QLabel {{ color: {accent}; }}")
        row.addWidget(title)
        row.addStretch()

        subtitle = QtWidgets.QLabel(self.group.subtitle, self.control)
        subtitle.setForegroundRole(_ROLE.PlaceholderText)
        subtitle.setFont(scaled_font(self.control, SMALL_POINTS))
        row.addWidget(subtitle, 0, _ALIGN.AlignBottom)
        header.addLayout(row)

        rule = QtWidgets.QFrame(self.control)
        rule.setFixedSize(*HEADER_RULE_SIZE)
        rule.setStyleSheet(f"QFrame {{ background: {accent}; border-radius: 1px; }}")
        header.addWidget(rule)

        return header

    @observe("group:visible_posts")
    def _show_cards(self, event=None):
        """The visible posts as cards, the first a lead card."""

        if self.control is None or self.group is None:
            return

        self._dispose_cards()
        accent = self._accent()

        for index, post in enumerate(self.group.visible_posts):
            card = FeedPostCard(
                post=post, controller=self.controller, lead=index == 0, accent=accent
            )
            self._cards_layout.addWidget(card.create(self.control))
            self._cards.append(card)

        hidden = self.group.hidden_count
        text = f"Show all ({len(self.group.posts)})" if hidden else "Show fewer"
        self._show_all.setText(_link_html(text, accent))
        self._show_all.setVisible(bool(hidden) or self.group.show_all)

    def _toggle_show_all(self, href):
        if self.controller is not None:
            self.controller.toggle_show_all(self.group)

    def _dispose_cards(self):
        for card in self._cards:
            control = card.control
            card.dispose()
            control.hide()
            control.deleteLater()

        self._cards = []


class _FeedScrollArea(QtWidgets.QScrollArea):
    """Asks for FEED_PREFERRED_HEIGHT; the pane decides what it gets."""

    def sizeHint(self):
        return QtCore.QSize(super().sizeHint().width(), FEED_PREFERRED_HEIGHT)


class _FeedGroupsEditor(Editor):
    """Shows the edited list of FeedGroups, or the empty state, scrolling;
    rebuilt when the palette changes."""

    #: One panel per group, top first.
    _panels = List(Instance(FeedGroupPanel))

    #: Whether a rebuild for a palette change is already queued.
    _rebuild_queued = Bool(False)

    def init(self, parent):
        self.control = scroll = _FeedScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        contents = ThemedWidget()
        contents.palette_changed.connect(self._queue_rebuild)
        layout = QtWidgets.QVBoxLayout(contents)
        layout.setContentsMargins(GRID, 0, GRID, 2 * GRID)
        layout.setSpacing(GRID)
        scroll.setWidget(contents)

    def update_editor(self):
        """Rebuild the panels for the current groups."""
        self._dispose_panels()

        contents = self.control.widget()
        layout = contents.layout()
        # The controller is the handler when the view runs through it.
        handler = self.ui.handler
        controller = handler if hasattr(handler, "toggle_show_all") else None

        while layout.count():
            item = layout.takeAt(0)

            if item.widget() is not None:
                item.widget().deleteLater()

        if not self.value:
            layout.addWidget(self._create_empty_state(contents))

        for group in self.value:
            panel = FeedGroupPanel(group=group, controller=controller)
            layout.addWidget(panel.create(contents))
            self._panels.append(panel)

        layout.addStretch()

    def dispose(self):
        self._dispose_panels()
        super().dispose()

    def _queue_rebuild(self):
        if not self._rebuild_queued:
            self._rebuild_queued = True
            QtCore.QTimer.singleShot(0, self._rebuild)

    def _rebuild(self):
        self._rebuild_queued = False

        if self.control is not None:
            self.update_editor()

    def _create_empty_state(self, parent):
        """A glyph and two muted lines, centred."""
        empty = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(empty)
        layout.setContentsMargins(2 * GRID, 5 * GRID, 2 * GRID, 5 * GRID)
        layout.setSpacing(GRID)
        muted = empty.palette().color(_ROLE.PlaceholderText).name()

        for widget in (
            _glyph_label(EMPTY_GLYPH, 4 * GRID, muted, empty),
            QtWidgets.QLabel(EMPTY_TITLE, empty),
            QtWidgets.QLabel(EMPTY_TEXT, empty),
        ):
            widget.setAlignment(_ALIGN.AlignCenter)
            widget.setWordWrap(True)
            layout.addWidget(widget)

        layout.itemAt(1).widget().setFont(scaled_font(empty, 2, bold=True))
        layout.itemAt(2).widget().setForegroundRole(_ROLE.PlaceholderText)

        return empty

    def _dispose_panels(self):
        for panel in self._panels:
            panel.dispose()

        self._panels = []


class FeedGroupsEditor(BasicEditorFactory):
    """Edit a list of FeedGroups as headed groups of cards."""

    klass = _FeedGroupsEditor


class _StatusBanner(QtWidgets.QFrame):
    """A rounded, tinted strip: the error colour on error, else muted."""

    def __init__(self):
        super().__init__()

        self.is_error = False

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        fill = QtGui.QColor(ERROR_COLOR) if self.is_error else palette.color(_ROLE.Mid)
        fill.setAlpha(28 if self.is_error else 60)
        edge = QtGui.QColor(fill)
        edge.setAlpha(110)

        painter.setPen(edge)
        painter.setBrush(fill)
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            CORNER_RADIUS,
            CORNER_RADIUS,
        )


class _StatusBannerEditor(Editor):
    """The status line as an inline banner with a glyph and a dismiss."""

    #: Whether the status reports a problem.
    is_error = Bool(False)

    #: The tinted strip, and its glyph and text labels.
    _banner = Any()
    _glyph = Any()
    _text = Any()

    def init(self, parent):
        self.control = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(self.control)
        outer.setContentsMargins(GRID, GRID, GRID, 0)

        self._banner = banner = _StatusBanner()
        outer.addWidget(banner)
        layout = QtWidgets.QHBoxLayout(banner)
        layout.setContentsMargins(GRID + GRID // 2, GRID, GRID, GRID)
        layout.setSpacing(GRID)

        self._glyph = _glyph_label("info", STATUS_GLYPH_SIZE, "", banner)
        layout.addWidget(self._glyph, 0, _ALIGN.AlignTop)

        self._text = QtWidgets.QLabel(banner)
        self._text.setWordWrap(True)
        self._text.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._text.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self._text, 1)

        dismiss = QtWidgets.QToolButton(banner)
        dismiss.setText("✕")
        dismiss.setAutoRaise(True)
        dismiss.setToolTip("Dismiss")
        dismiss.clicked.connect(self._dismiss)
        layout.addWidget(dismiss, 0, _ALIGN.AlignTop)

        self.sync_value(self.factory.error_name, "is_error", "from")

    def update_editor(self):
        self._text.setText(self.str_value)

    @observe("is_error")
    def _show_error_state(self, event):
        if self.control is None:
            return

        muted = self.control.palette().color(_ROLE.PlaceholderText).name()
        color = ERROR_COLOR if self.is_error else muted

        self._banner.is_error = self.is_error
        self._glyph.setText("error" if self.is_error else "info")
        self._glyph.setStyleSheet(f"QLabel {{ color: {color}; }}")
        self._banner.update()

    def _dismiss(self):
        handler = self.ui.handler

        if hasattr(handler, "dismiss_status"):
            handler.dismiss_status()


class StatusBannerEditor(BasicEditorFactory):
    """Show a status Str as an inline banner; error-tinted on error."""

    klass = _StatusBannerEditor

    #: The extended name of the Bool saying the status is an error.
    error_name = Str()


SciBotsFeedView = View(
    VGroup(
        UItem(
            "status_text",
            editor=StatusBannerEditor(error_name="status_is_error"),
            visible_when="status_text",
        ),
        UItem("groups", editor=FeedGroupsEditor()),
    ),
    resizable=True,
    width=420,
    height=720,
    title="Sci-Bots Feed",
)
