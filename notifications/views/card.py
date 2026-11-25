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
    ▌      Source · 3 min ago · ×2               ┌───────┐
    ▌      Two lines of the detail, with a       │ thumb │
    ▌      file name as a link, then an ellip…   └───────┘
    ▌      [ Primary ]  How do I…?                 Show more

The thumbnail shows only when the entry has one; a click on it presses the
primary button. A card with help and nothing to press shows the help as its
one control, an outlined button. While nothing can open help, help is
disabled and says so. Runs standalone against just an entry::

    NotificationCard(Notification(title="Hello", detail="World")).show()

The card only reports clicks, through its signals; whoever holds it acts.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_CLOSE, ICON_HELP
from microdrop_style.palette_helpers import icon_font
from microdrop_style.panel_theme import (
    outlined_button_icon,
    theme_palette,
)
from microdrop_style.typography import BODY_TEXT, CARD_TITLE, META, role_font

# Microdrop utils imports.
from microdrop_utils.new_marker import NewDot

# Local imports.
from ..consts import SEVERITY_GLYPHS, HelpAction
from ..models.notification import Notification
from .card_parts import (
    STRIPE_WIDTH,
    CardBody,
    CardFooter,
    FlashFade,
    TracebackView,
    card_style_sheet,
    card_tooltip,
    meta_text,
    paint_card,
    palette_key,
    restyle_by_name,
    stripe_color,
)
from .card_thumbnail import CardThumbnail
from .formatting import format_preview
from .view_consts import CARD_BODY_LINES, THUMBNAIL_SIZE, TOAST_THUMBNAIL_SIZE

#: Pixel size of the severity glyph.
GLYPH_SIZE = 20

#: A section alert's glyph, in its accent.
ALERT_GLYPH = "fiber_new"

#: What a disabled help link says.
HELP_UNAVAILABLE_TOOLTIP = "Help for this is not available yet"

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

    #: The second button: a help link or "Later".
    secondary_clicked = QtCore.Signal(object)

    #: "Show more" / "Show less", or a click on a drawer card's body.
    expand_clicked = QtCore.Signal(object)

    #: A click on a toast's body.
    body_clicked = QtCore.Signal(object)

    #: A link in the detail, with its path.
    link_clicked = QtCore.Signal(object, str)

    def __init__(self, entry, parent=None, toast=False, help_available=True):
        super().__init__(parent)

        self.entry = entry
        self.toast = toast
        self.help_available = help_available

        #: A toast's time left, 0-1; None draws no countdown.
        self.progress = None

        self._hovered = False
        self._palette_key = None

        #: The highlight, fading after ``flash()``.
        self._flash = FlashFade(self)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        # Its height for its width, every pass: a Maximum policy capped it
        # at its size hint, taken at another width, cutting wrapped text.
        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        self._build()
        self._binding = _CardBinding(entry=entry, card=self)
        self._apply_style()
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
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred
        )
        top.addWidget(self._title, 1, _ALIGN.AlignTop)

        self._new_dot = NewDot(self)
        top.addWidget(self._new_dot, 0, _ALIGN.AlignTop)

        self._dismiss = QtWidgets.QToolButton(self)
        self._dismiss.setObjectName("cardDismiss")
        self._dismiss.setText(ICON_CLOSE)
        self._dismiss.setToolTip(
            "Hide (it stays in notifications)" if self.toast else "Dismiss"
        )
        self._dismiss.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self._dismiss.clicked.connect(lambda: self.dismiss_clicked.emit(self.entry))
        top.addWidget(self._dismiss, 0, _ALIGN.AlignTop)
        column.addLayout(top)

        # The meta line and the detail, the thumbnail (made when there is
        # one) at their right: the card is as tall as the taller.
        self._beside = QtWidgets.QHBoxLayout()
        self._beside.setContentsMargins(0, 0, 0, 0)
        self._beside.setSpacing(10)
        self._thumbnail = None
        column.addLayout(self._beside)

        text = QtWidgets.QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        self._beside.addLayout(text, 1)

        self._meta = QtWidgets.QLabel(self)
        self._meta.setObjectName("cardMeta")
        self._meta.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed
        )
        text.addWidget(self._meta)
        text.addSpacing(4)

        self._body = CardBody(self, CARD_BODY_LINES, keyboard=not self.toast)
        self._body.overflow_changed.connect(self._show_more_link)
        self._body.link_clicked.connect(
            lambda path: self.link_clicked.emit(self.entry, path)
        )
        text.addWidget(self._body)
        text.addStretch(1)

        # Made the first time a traceback is expanded.
        self._traceback = None
        self._column = column

        # The buttons, then "Show more" at the far end, on one row or two.
        self._footer = CardFooter(self)
        self._footer.primary.clicked.connect(
            lambda: self.action_clicked.emit(self.entry)
        )
        self._footer.secondary.clicked.connect(
            lambda: self.secondary_clicked.emit(self.entry)
        )
        self._footer.more.clicked.connect(lambda: self.expand_clicked.emit(self.entry))
        column.addWidget(self._footer)

        self._acted = QtWidgets.QLabel(self)
        self._acted.setObjectName("cardActed")
        self._acted.hide()
        column.addWidget(self._acted)

    # ------------------------------------------------------------------ #
    # Showing the entry                                                   #
    # ------------------------------------------------------------------ #

    def refresh(self):
        """Show the entry as it is now."""
        entry = self.entry

        if entry.section_id:
            self._glyph.setText(ALERT_GLYPH)
            self._glyph.setStyleSheet(
                f"color: {stripe_color(entry, theme_palette()).name()};"
            )

        else:
            self._glyph.setText(SEVERITY_GLYPHS[entry.severity])
            # A thread's entry can change severity: the colour follows.
            restyle_by_name(self._glyph, f"cardGlyph_{entry.severity}")

        bold = self.toast or entry.unread or entry.needs_attention
        self._title.setFont(
            role_font(CARD_TITLE, None if bold else QtGui.QFont.Weight.Medium)
        )
        self._title.setText(entry.title)

        self._new_dot.setVisible(not self.toast and entry.is_new)
        self.refresh_time()
        self._show_body()
        self._show_buttons()
        self._show_thumbnail()

        self._acted.setVisible(bool(entry.acted))
        self._acted.setText(f"✓  {entry.acted}")

        self.setToolTip(card_tooltip(entry))
        self.update()

    def set_help_available(self, available):
        """Enable the help link, or disable it saying why."""

        if available != self.help_available:
            self.help_available = available
            self._show_buttons()

    def refresh_time(self):
        """Show the time since the entry, which runs on."""
        metrics = QtGui.QFontMetrics(self._meta.font())
        text = meta_text(self.entry)

        self._meta.setText(
            metrics.elidedText(text, _ELIDE, max(self._meta.width(), 60))
        )

    def flash(self):
        """Highlight the card, fading out: "this is the one"."""
        self._flash.start()

    def set_progress(self, progress):
        """Draw a toast's countdown at ``progress`` (0-1), or none."""

        if progress != self.progress:
            self.progress = progress
            self.update()

    def dispose(self):
        """Stop following the entry."""
        self._binding.entry = None

    def _show_body(self):
        entry = self.entry
        traceback = entry.monospace_detail
        expanded = entry.expanded and not self.toast

        self._body.setVisible(bool(entry.detail) and not (traceback and expanded))
        self._body.show_detail(
            format_preview(entry) if traceback else entry.detail,
            lines=0 if expanded else CARD_BODY_LINES,
            links=entry.links,
        )

        if traceback and expanded:
            self._show_traceback()

        elif self._traceback is not None:
            self._traceback.hide()

        self._show_more_link()

    def _show_traceback(self):

        if self._traceback is None:
            self._traceback = TracebackView(self)
            index = self._column.indexOf(self._footer)
            self._column.insertWidget(index, self._traceback)

        self._traceback.show_detail(self.entry.detail)

    def _expandable(self):
        entry = self.entry
        expandable = entry.monospace_detail or self._body.overflowed or entry.expanded

        return bool(entry.detail) and expandable

    def _show_more_link(self, *args):
        expandable = self._expandable()
        more = self._footer.more

        more.setVisible(not self.toast and expandable)
        more.setText("Show less" if self.entry.expanded else "Show more")
        self._footer.show_controls()

        # The hand only where a click does something.
        self.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
            if self.toast or expandable
            else QtCore.Qt.CursorShape.ArrowCursor
        )

    def _show_buttons(self):
        """The primary button, and the help link or "Later": help as a link
        beside a primary button, or the card's one outlined control when
        there is nothing to press; disabled while nothing opens help."""
        entry = self.entry
        primary, secondary = self._footer.primary, self._footer.secondary
        action, second = entry.action, entry.secondary_action
        is_help = isinstance(second, HelpAction)

        if action is not None:
            primary.setText(action.label)

        primary.setVisible(action is not None and not entry.acted)

        if second is not None:
            secondary.setText(second.label)

        if is_help:
            secondary.setEnabled(self.help_available)
            secondary.setToolTip(
                f"Open help: {second.target}"
                if self.help_available
                else HELP_UNAVAILABLE_TOOLTIP
            )

        else:
            secondary.setEnabled(True)
            secondary.setToolTip("Move this out of Needs attention, for later")

        secondary.setVisible(second is not None and not entry.acted)

        help_only = is_help and action is None
        name = "cardHelpOnly" if help_only else ("cardHelp" if is_help else "cardLater")
        ratio = self.devicePixelRatioF()
        icon = outlined_button_icon(ICON_HELP, theme_palette(), ratio)

        secondary.setIcon(icon if help_only else QtGui.QIcon())
        restyle_by_name(secondary, name)
        self._footer.show_controls()

    def _show_thumbnail(self):
        """The entry's picture beside the text, its box made the first time
        there is one; a click on it presses the card's button."""

        if self.entry.thumbnail and self._thumbnail is None:
            size = TOAST_THUMBNAIL_SIZE if self.toast else THUMBNAIL_SIZE
            self._thumbnail = CardThumbnail(size, self)
            self._thumbnail.clicked.connect(
                lambda: self.action_clicked.emit(self.entry)
            )
            self._beside.addWidget(self._thumbnail, 0, _ALIGN.AlignTop)

        if self._thumbnail is not None:
            self._thumbnail.show_entry(self.entry)

    # ------------------------------------------------------------------ #
    # Style                                                               #
    # ------------------------------------------------------------------ #

    def _apply_style(self):
        """One shared style sheet for the card's parts, by object name.
        Returns whether the theme changed since it was last applied."""
        palette = theme_palette()
        key = palette_key(palette)

        if key == self._palette_key:
            return False

        self._palette_key = key
        self._meta.setFont(role_font(META))
        self._acted.setFont(role_font(META))
        self._body.setFont(role_font(BODY_TEXT))
        self.setStyleSheet(card_style_sheet(palette))

        return True

    def _restyle(self):
        """Follow a theme change: colours that are not in the style sheet
        (an alert's glyph, the help icon) are set again by a refresh."""

        if self._apply_style():
            self.refresh()

    def event(self, event):

        if event.type() in _PALETTE_EVENTS:
            QtCore.QTimer.singleShot(0, self._restyle)

        return super().event(event)

    # ------------------------------------------------------------------ #
    # Painting and clicks                                                 #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        palette = theme_palette()

        paint_card(
            QtGui.QPainter(self),
            self.rect(),
            palette,
            stripe_color(self.entry, palette),
            hovered=self._hovered and not self.toast,
            flash=self._flash.value,
            progress=self.progress,
        )

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

        elif self._expandable():
            self.expand_clicked.emit(self.entry)

        event.accept()
