# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Where each part of a notification card goes, from its row's rectangle.

One layout serves painting, the row's size, hit-testing clicks and placing
the expanded detail, so they cannot disagree::

    | ▌(!) Title, bold while unread ............... 14:03:22  ✕ |
    | ▌    ×3  log · device_viewer          [ Action ]   ⌄     |
    | ▌    First line of the detail, while collapsed...         |
    | ▌    ┌ the selectable detail, while expanded ┐            |
"""

# Standard library imports.
from collections import namedtuple

# Enthought library imports.
from pyface.qt import QtCore, QtGui

# Local imports.
from ..consts import DETAIL_MAX_HEIGHT
from .formatting import format_time

#: Gap between cards, and between a card and the list's edges.
CARD_MARGIN = 6

#: Inside a card, between its border and its contents.
CARD_PADDING = 8

#: Width of the severity strip down a card's left edge.
ACCENT_WIDTH = 4

#: Between parts on one line, and between lines.
GAP = 6

#: Horizontal padding inside the action button and the count pill.
PILL_PADDING = 8

#: Allowance for the detail viewer's document margins.
DETAIL_FRAME = 10


#: One card's parts, as QRects; ``None`` for a part the entry has not.
#: ``time_text`` is the text in ``time``; ``height`` the row's.
CardLayout = namedtuple(
    "CardLayout",
    [
        "card",
        "glyph",
        "title",
        "time",
        "time_text",
        "dismiss",
        "count",
        "meta",
        "action",
        "chevron",
        "preview",
        "detail",
        "height",
    ],
)


def detail_height(entry, width, font, monospace_font):
    """Pixels the expanded detail takes at ``width``, at most
    DETAIL_MAX_HEIGHT (the viewer scrolls past that)."""

    if entry.monospace_detail:
        metrics = QtGui.QFontMetrics(monospace_font)
        lines = entry.detail.count("\n") + 1
        # Unwrapped: room for a horizontal scroll bar under the lines.
        height = lines * metrics.lineSpacing() + metrics.height()

    else:
        metrics = QtGui.QFontMetrics(font)
        bounds = metrics.boundingRect(
            QtCore.QRect(0, 0, max(width - DETAIL_FRAME, 1), 100_000),
            QtCore.Qt.TextFlag.TextWordWrap,
            entry.detail,
        )
        height = bounds.height()

    return min(height + DETAIL_FRAME, DETAIL_MAX_HEIGHT)


def layout_card(rect, entry, font, monospace_font, glyph_size, now=None):
    """Lay out ``entry``'s card in the row ``rect`` (its height ignored), its
    time relative to ``now`` (seconds since the epoch; the current time if
    None)."""
    metrics = QtGui.QFontMetrics(font)
    line = metrics.height()

    card_left = rect.left() + CARD_MARGIN
    card_right = rect.right() - CARD_MARGIN
    top = rect.top() + CARD_MARGIN // 2 + CARD_PADDING
    left = card_left + ACCENT_WIDTH + CARD_PADDING
    right = card_right - CARD_PADDING

    # First line: glyph, title, time and the dismiss cross.
    glyph = QtCore.QRect(left, top, glyph_size, max(glyph_size, line))
    text_left = glyph.right() + 1 + GAP
    dismiss = QtCore.QRect(right - line + 1, top, line, line)
    time_text = format_time(entry.last_seen, now)
    # A pixel spare: advances are rounded, and elision is exact.
    time_width = metrics.horizontalAdvance(time_text) + 2
    time = QtCore.QRect(dismiss.left() - GAP - time_width, top, time_width, line)
    title = QtCore.QRect(text_left, top, time.left() - GAP - text_left, line)

    # Second line: count pill, meta text, action button and chevron.
    y = top + max(line, glyph.height()) + GAP // 2
    row_height = line + 4
    end = right + 1
    chevron = None
    action = None
    count = None

    if entry.detail:
        chevron = QtCore.QRect(end - line, y, line, row_height)
        end = chevron.left() - GAP

    if entry.action is not None:
        width = metrics.horizontalAdvance(entry.action.label) + 2 * PILL_PADDING
        action = QtCore.QRect(end - width, y, width, row_height)
        end = action.left() - GAP

    meta_left = text_left

    if entry.count > 1:
        width = metrics.horizontalAdvance(f"×{entry.count}") + PILL_PADDING
        count = QtCore.QRect(text_left, y + 2, width, line)
        meta_left = count.right() + 1 + GAP

    meta = QtCore.QRect(meta_left, y, max(end - meta_left, 0), row_height)
    y += row_height + GAP // 2

    # Then the detail: its first line while collapsed, all of it expanded.
    preview = None
    detail = None
    detail_width = right + 1 - text_left

    if entry.detail and entry.expanded:
        height = detail_height(entry, detail_width, font, monospace_font)
        detail = QtCore.QRect(text_left, y, detail_width, height)
        y += height + GAP // 2

    elif entry.detail:
        preview = QtCore.QRect(text_left, y, detail_width, line)
        y += line + GAP // 2

    bottom = y + CARD_PADDING
    card = QtCore.QRect(
        card_left, rect.top() + CARD_MARGIN // 2, card_right - card_left + 1, 0
    )
    card.setBottom(bottom - 1)

    return CardLayout(
        card=card,
        glyph=glyph,
        title=title,
        time=time,
        time_text=time_text,
        dismiss=dismiss,
        count=count,
        meta=meta,
        action=action,
        chevron=chevron,
        preview=preview,
        detail=detail,
        height=bottom + CARD_MARGIN // 2 - rect.top(),
    )
