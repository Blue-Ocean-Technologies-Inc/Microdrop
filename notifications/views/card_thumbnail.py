# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A card's small picture: a rounded box of fixed size, there from the
moment the card is built so nothing shifts when the picture arrives.

The picture is asked for once the box shows, decoded off the GUI thread
(``microdrop_utils.image_thumbnails``), and a new path replaces it in place:
the old picture stays until the new one is ready. A file that is missing or
no readable image (a video, say) shows a placeholder glyph of its kind.
"""

# Standard library imports.
import mimetypes
from functools import partial
from pathlib import Path

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.palette_helpers import icon_font, mix, rounded_path
from microdrop_style.panel_theme import card_border, muted_text, theme_palette

# Microdrop utils imports.
from microdrop_utils.image_thumbnails import thumbnail_loader

#: Corner radius (px) of the box.
THUMBNAIL_RADIUS = 6

#: Pixel size of the placeholder glyph.
PLACEHOLDER_GLYPH_SIZE = 24

#: The placeholder glyphs: a picture, and a film for a video.
IMAGE_GLYPH = "image"
VIDEO_GLYPH = "movie"

#: Video files the platform's type table may not know.
VIDEO_SUFFIXES = frozenset({".mkv", ".mp4", ".avi", ".mov", ".webm"})

#: How much of the text colour tints the empty box.
PLACEHOLDER_TINT = 0.07

_ROLE = QtGui.QPalette.ColorRole
_LEFT = QtCore.Qt.MouseButton.LeftButton


def is_video(path):
    """Whether ``path`` names a video file, by its name alone."""
    kind = mimetypes.guess_type(str(path), strict=False)[0] or ""

    return kind.startswith("video/") or Path(path).suffix.lower() in VIDEO_SUFFIXES


class CardThumbnail(QtWidgets.QWidget):
    """A ``size`` (width, height px) box showing the picture at ``path``.
    While ``clickable`` it takes clicks (``clicked``); else they reach the
    card beneath."""

    clicked = QtCore.Signal()

    def __init__(self, size, parent=None):
        super().__init__(parent)

        self.path = ""
        self.clickable = False

        self._pixmap = None
        self._failed = False

        #: The path whose picture was asked for.
        self._requested = ""

        # Asked for in the turn after showing: the card shows first. A
        # timer of the box's own, so a deleted box is never called.
        self._load_timer = QtCore.QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(0)
        self._load_timer.timeout.connect(self._load)

        self.setFixedSize(*size)

    def show_entry(self, entry):
        """Follow ``entry``: its thumbnail, and whether a click runs its
        action; a handled card's button is spent, its thumbnail is not."""
        clickable = entry.action is not None

        self.clickable = clickable
        self.setToolTip(entry.action.label if clickable else "")

        # Not clickable, it is part of the card: the card's cursor shows.
        if clickable:
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        else:
            self.unsetCursor()

        self.setVisible(bool(entry.thumbnail))
        self.show_path(entry.thumbnail)

    def show_path(self, path):
        """Show the picture at ``path``; the one shown stays until it is
        ready."""

        if path == self.path:
            return

        self.path = path
        self._requested = ""

        if self.isVisible():
            self._load_timer.start()

    def showEvent(self, event):
        super().showEvent(event)

        self._load_timer.start()

    def _load(self):
        path = self.path

        if not path or path == self._requested or not self.isVisible():
            return

        self._requested = path

        # A video is never decoded: it shows its glyph.
        if is_video(path):
            self._show(path, None)

            return

        size = (self.width(), self.height())
        callback = partial(self._show, path)
        thumbnail_loader().request(path, size, self.devicePixelRatioF(), callback)

    def _show(self, path, pixmap):

        # A late picture: the card moved on to another meanwhile.
        if path != self.path:
            return

        self._pixmap = pixmap
        self._failed = pixmap is None

        try:
            self.update()

        # The card was deleted while its picture decoded: nothing to show.
        except RuntimeError:
            pass

    def paintEvent(self, event):
        palette = theme_palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        box = rounded_path(self.rect(), THUMBNAIL_RADIUS)

        fill = mix(
            palette.color(_ROLE.Base), palette.color(_ROLE.Text), PLACEHOLDER_TINT
        )
        painter.fillPath(box, fill)
        painter.setClipPath(box)

        if self._pixmap is not None and not self._failed:
            size = self._pixmap.deviceIndependentSize()
            corner = QtCore.QPointF(
                (self.width() - size.width()) / 2, (self.height() - size.height()) / 2
            )
            painter.drawPixmap(corner, self._pixmap)

        elif self._failed:
            painter.setFont(icon_font(PLACEHOLDER_GLYPH_SIZE))
            painter.setPen(muted_text(palette))
            painter.drawText(
                self.rect(),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                VIDEO_GLYPH if is_video(self.path) else IMAGE_GLYPH,
            )

        painter.setClipping(False)
        painter.strokePath(box, QtGui.QPen(card_border(palette), 1))
        painter.end()

    def mousePressEvent(self, event):

        if self.clickable and event.button() == _LEFT:
            event.accept()

            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        inside = self.rect().contains(event.position().toPoint())

        if self.clickable and event.button() == _LEFT:
            event.accept()

            if inside:
                self.clicked.emit()

            return

        super().mouseReleaseEvent(event)
