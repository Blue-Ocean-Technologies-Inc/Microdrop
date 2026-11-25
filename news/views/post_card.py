# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A feed post as a card: a lead card (picture as a banner on top, large
title) or a compact row (title, meta line, small picture at the right).

News, not alerts: no severity strip; the kind is a small label in the
group's accent. Cards are painted from their palette, so they follow the
theme, also a preview's; spacing is on an 8-pixel grid. Clicking a card
that has a summary shows or hides it; a compact row without one is itself
the post's link. Links go to the controller.
"""

# Standard library imports.
from functools import partial
from html import escape

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, Dict, HasTraits, Instance, Int, List, Str, observe

# Microdrop utils imports.
from microdrop_utils.rich_text_clamp import clamp_rich_text

# Local imports.
from ..models.feed_model import (
    ORIGIN_PUSHED,
    FeedPost,
    format_post_date,
    summary_teaser,
)
from ..services.thumbnails import thumbnail_loader
from .card_style import (
    BANNER_LOADING_HEIGHT,
    COMPACT_TITLE_LINES,
    COMPACT_TITLE_POINTS,
    GRID,
    KIND_LABELS,
    LEAD_TITLE_LINES,
    LEAD_TITLE_POINTS,
    READ_MORE_HREF,
    RELEASE_COLLAPSED_LINES,
    REMOVE_HREF,
    SMALL_POINTS,
    SUMMARY_COLLAPSED_LINES,
    TAG_TINT,
    THUMBNAIL_SIZE,
    blend,
    cropped,
    fitted,
    full_width_picture_height,
    release_summary_html,
    scaled_font,
)
from .card_widgets import (
    CardFrame,
    ElidedLine,
    PicturePair,
    Thumbnail,
    show_picture_preview,
)

_ROLE = QtGui.QPalette.ColorRole
_ALIGN = QtCore.Qt.AlignmentFlag
_PALETTE_EVENTS = (
    QtCore.QEvent.Type.PaletteChange,
    QtCore.QEvent.Type.ApplicationPaletteChange,
)


class FeedPostCard(HasTraits):
    """One post's card, lead or compact; a lead card with two pictures shows
    them side by side."""

    #: The post shown.
    post = Instance(FeedPost)

    #: The SciBotsFeedController its clicks go to; None ignores them.
    controller = Any()

    #: Whether it is its group's lead card.
    lead = Bool(False)

    #: The group's accent, a colour name: its kicker.
    accent = Str()

    #: The colour of its links (Read more, Show more); the accent if empty.
    link_color = Str()

    #: Fonts by part ("title", "small", "body", "link") from a host with its own
    #: type roles; a part not given is the card's font resized.
    fonts = Dict(Str, Any)

    #: The card.
    control = Any()

    #: The summary label and the "Show more" note.
    _summary = Any()
    _more = Any()

    #: ``(label, html)`` of the labels holding links.
    _link_labels = List()

    #: The whole summary as rich text, links styled; the collapsed card
    #: shows it cut to whole lines.
    _summary_html = Str()

    #: The compact row's picture.
    _thumbnail = Any()

    #: A compact release row's first feature, shown while collapsed.
    _teaser = Any()

    #: The loaded picture, and its size known before then (QSize or None).
    _picture = Any()
    _picture_size = Any()

    #: A lead card's two pictures, and their loaded pixmaps.
    _pair = Any()
    _pair_pixmaps = Dict(Int, Any)

    def create(self, parent):
        """Build the card."""
        post = self.post
        self.control = card = CardFrame(parent)
        card.resized.connect(self._on_resized)

        if self._has_summary():
            card.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(self._toggle)

        elif self._is_link_row():
            card.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(lambda: self._open_link(READ_MORE_HREF))

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(2 * GRID, 2 * GRID, 2 * GRID, GRID + GRID // 2)
        layout.setSpacing(GRID)

        pair = self.lead and len(post.images) == 2

        if pair:
            layout.addWidget(self._create_pair())

        if self.lead:
            layout.addWidget(self._create_meta())
            layout.addWidget(self._create_title(LEAD_TITLE_LINES, LEAD_TITLE_POINTS))

        else:
            layout.addLayout(self._create_compact_head())

        self._summary = self._create_summary()
        layout.addWidget(self._summary)
        layout.addLayout(self._create_footer())

        self._render_links()

        if pair:
            for index, (src, _caption, _alt) in enumerate(post.images):
                thumbnail_loader().request(src, partial(self._show_pair_picture, index))

        elif post.image:
            self._show_loading()
            thumbnail_loader().request(post.image, self._show_picture)

        self._show_expanded()

        return card

    def dispose(self):
        """Let go of the post and the widgets; the caller deletes the card."""
        self.trait_set(
            post=None,
            controller=None,
            _summary=None,
            _more=None,
            _link_labels=[],
            _thumbnail=None,
            _teaser=None,
            _pair=None,
            _pair_pixmaps={},
        )

    # ------------------------------------------------------------------ #
    # Building                                                            #
    # ------------------------------------------------------------------ #

    def _has_summary(self):
        return bool(self.post.summary or self.post.summary_html)

    def _is_link_row(self):
        """Whether it is a compact row with nothing to expand, so the row
        itself opens the post instead of a "Read more" line."""
        return not self.lead and not self._has_summary()

    def _create_meta(self):
        """ "NEWSLETTER · Sci-Bots · September 2026": the kind in the accent,
        the rest muted."""
        post = self.post
        parts = [post.source_label, format_post_date(post)]
        separator = "&nbsp;&nbsp;·&nbsp;&nbsp;"
        rest = separator.join(escape(part) for part in parts if part)
        muted = self.control.palette().color(_ROLE.PlaceholderText).name()
        kind = KIND_LABELS[post.kind].upper()

        label = QtWidgets.QLabel(self.control)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setFont(self._font("small", SMALL_POINTS))
        label.setText(
            f'<span style="color: {self.accent}; font-weight: 700;">{kind}</span>'
            f'<span style="color: {muted};">{separator}{rest}</span>'
        )

        return label

    def _create_title(self, lines, points):
        title = ElidedLine(self.post.title, lines, self.control)
        title.setFont(self._font("title", points, bold=True))

        return title

    def _create_compact_head(self):
        """Meta over title (over a release's first feature) at the left, the
        picture at the right."""
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(GRID + GRID // 2)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(GRID // 2)

        text.addWidget(self._create_meta())
        text.addWidget(self._create_title(COMPACT_TITLE_LINES, COMPACT_TITLE_POINTS))

        teaser = summary_teaser(self.post)

        if self.post.kind == "release" and teaser:
            self._teaser = ElidedLine(teaser, 1, self.control)
            self._teaser.setForegroundRole(_ROLE.PlaceholderText)
            text.addWidget(self._teaser)

        text.addStretch()
        head.addLayout(text, 1)

        if self.post.image:
            self._thumbnail = Thumbnail(self.control)
            head.addWidget(self._thumbnail, 0, _ALIGN.AlignTop)

        return head

    def _create_summary(self):
        """The rich summary if there is one, else the plain one."""
        post = self.post
        summary = QtWidgets.QLabel(self.control)
        summary.setFont(self._font("body", 0))
        summary.setWordWrap(True)
        summary.setAlignment(_ALIGN.AlignLeft | _ALIGN.AlignTop)

        # Plain text too goes through rich text: the collapsed summary is
        # cut by the rich text layout.
        summary.setTextFormat(QtCore.Qt.TextFormat.RichText)

        if post.summary_html:
            html = post.summary_html
            palette = self.control.palette()

            if post.kind == "release":
                accent = QtGui.QColor(self.accent)
                tag_fill = blend(palette.color(_ROLE.Base), accent, TAG_TINT)
                html = release_summary_html(
                    html,
                    self.accent,
                    tag_fill.name(),
                    palette.color(_ROLE.PlaceholderText).name(),
                )

            summary.setOpenExternalLinks(False)
            summary.setToolTip(post.summary)
            summary.linkActivated.connect(self._open_link)
            self._link_labels.append((summary, html))

        else:
            self._link_labels.append(
                (summary, f"<p>{escape(post.summary).replace(chr(10), '<br>')}</p>")
            )

        summary.setVisible(bool(post.summary or post.summary_html))

        return summary

    def _create_footer(self):
        """ "Show more" at the left; Remove (pushed) and Read more (but on a
        link row) at the right, in the accent."""
        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(2 * GRID)

        self._more = QtWidgets.QLabel(self.control)
        self._more.setForegroundRole(_ROLE.PlaceholderText)

        # A host's link colour makes it read as the click it is.
        if self.link_color:
            self._more.setForegroundRole(_ROLE.WindowText)
            self._more.setStyleSheet(f"QLabel {{ color: {self.link_color}; }}")
        self._more.setFont(self._font("small", SMALL_POINTS))
        footer.addWidget(self._more)
        footer.addStretch()

        links = [] if self._is_link_row() else [("Read more ›", READ_MORE_HREF)]

        if self.post.origin == ORIGIN_PUSHED:
            links.insert(0, ("Remove", REMOVE_HREF))

        for text, href in links:
            label = QtWidgets.QLabel(self.control)
            label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            label.setOpenExternalLinks(False)
            label.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            label.setFont(self._font("link", 0))
            label.linkActivated.connect(self._open_link)
            text = f"<b>{text}</b>" if href == READ_MORE_HREF else text
            self._link_labels.append((label, f'<a href="{href}">{text}</a>'))
            footer.addWidget(label)

        return footer

    # ------------------------------------------------------------------ #
    # Reactions                                                           #
    # ------------------------------------------------------------------ #

    def _render_links(self):
        """Links in the accent, not underlined: Qt's HTML import would take
        the application's link colour, which a preview does not use."""
        style = f"color: {self.link_color or self.accent}; text-decoration: none;"

        for label, html in self._link_labels:
            styled = html.replace("<a ", f'<a style="{style}" ')

            if label is self._summary:
                self._summary_html = styled

            label.setText(styled)

        self._show_expanded()

    def _open_link(self, href):
        if self.controller is None or self.post is None:
            return

        if href == READ_MORE_HREF:
            self.controller.open_post(self.post)

        elif href == REMOVE_HREF:
            self.controller.remove(self.post.id)

        else:
            self.controller.open_link(href)

    def _font(self, part, points, bold=False):
        """The host's font for ``part``, or the card's resized by
        ``points``."""
        font = self.fonts.get(part)

        if font is None:
            return scaled_font(self.control, points, bold)

        return QtGui.QFont(font)

    def _create_pair(self):
        images = self.post.images
        self._pair = PicturePair(
            [caption for _src, caption, _alt in images],
            [alt for _src, _caption, alt in images],
            self.control,
        )
        self._pair.sizes = [thumbnail_loader().known_size(src) for src, *_ in images]
        self._pair.setFont(self._font("small", SMALL_POINTS))
        self._pair.picture_clicked.connect(self._preview_picture)

        return self._pair

    def _show_pair_picture(self, index, pixmap):

        if self._pair is not None and pixmap is not None:
            self._pair_pixmaps[index] = pixmap
            self._pair.set_picture(index, pixmap)

    def _preview_picture(self, index):
        """The picture larger; the post's link while it is still loading."""
        pixmap = self._pair_pixmaps.get(index)

        if pixmap is None:
            self._open_link(READ_MORE_HREF)

            return

        show_picture_preview(pixmap, self.post.images[index][1], self.control.window())

    def _toggle(self):
        if self.controller is not None and self.post is not None:
            self.controller.toggle_expanded(self.post)

    def _on_resized(self):
        self._show_expanded()
        self._show_banner()

    @observe("post:expanded", post_init=True)
    def _show_expanded(self, event=None):
        """A lead card shows its summary's first lines, a compact row none,
        until expanded."""

        if self._summary is None or self.post is None:
            return

        summary = self._summary
        has_summary = self._has_summary()
        lines = 0

        if self.lead:
            release = self.post.kind == "release"
            lines = RELEASE_COLLAPSED_LINES if release else SUMMARY_COLLAPSED_LINES

        full = self._summary_html
        collapsed, overflows = full, True

        if lines:
            collapsed, overflows = clamp_rich_text(
                full, summary.font(), summary.width(), lines
            )

        text = full if self.post.expanded else collapsed

        if summary.text() != text:
            summary.setText(text)

        summary.setVisible(has_summary and (self.post.expanded or lines > 0))
        self._more.setVisible(has_summary and overflows)
        self._more.setText("Show less" if self.post.expanded else "Show more")

        if self._teaser is not None:
            self._teaser.setVisible(not self.post.expanded)

    def _show_loading(self):
        """A lead card's banner placeholder, at the picture's own height if
        its size is known (``_show_banner``): the card keeps its size."""

        if self.lead:
            self._picture_size = thumbnail_loader().known_size(self.post.image)
            self._set_banner("loading", BANNER_LOADING_HEIGHT)
            self._show_banner()

    def _show_picture(self, pixmap):
        """Show the loaded picture; None removes its placeholder."""

        if self.post is None:
            return

        if pixmap is None:
            self._picture_size = None

            if self.lead:
                self._set_banner(None, 0)

            elif self._thumbnail is not None:
                self._thumbnail.hide()

            return

        self._picture = pixmap

        if self.lead:
            self._show_banner()

        elif self._thumbnail is not None:
            ratio = self.control.devicePixelRatioF()
            self._thumbnail.pixmap = fitted(pixmap, *THUMBNAIL_SIZE, ratio)
            self._thumbnail.update()

    def _show_banner(self):
        """The picture across the card's top, edge to edge at its own
        aspect, cropped top and bottom past the cap
        (``full_width_picture_height``); never padded. Until it loads, its
        placeholder at that height, if its size is known."""

        if not self.lead or self.control is None:
            return

        loaded = self._picture is not None
        picture = self._picture_size

        if loaded:
            picture = self._picture.deviceIndependentSize()

        if picture is None:
            return

        width = self.control.width()
        height = full_width_picture_height(width, picture.width(), picture.height())
        ratio = self.control.devicePixelRatioF()
        banner = cropped(self._picture, width, height, ratio) if loaded else "loading"

        self._set_banner(banner, height)

    def _set_banner(self, banner, height):
        card = self.control
        card.banner = banner
        card.banner_height = height
        margins = card.layout().contentsMargins()
        margins.setTop(height + 2 * GRID)
        card.layout().setContentsMargins(margins)
        card.update()
