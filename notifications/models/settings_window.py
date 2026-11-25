# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The settings window's own state for the session, Qt-free: its size, its
tab, and which "By kind" sections are expanded; with the rules the window
follows for them. Nothing here is saved to disk."""

# Enthought library imports.
from traits.api import Bool, Dict, HasTraits, Int, Str, Tuple

#: The window's size (px) at first, and the least it can be made.
DEFAULT_WINDOW_SIZE = (540, 600)
MIN_WINDOW_SIZE = (420, 340)

#: Most of the screen's available height (0-1) the window opens to.
MAX_SCREEN_HEIGHT_FRACTION = 0.8

#: Kinds in all past which only the first section starts expanded; at or
#: under it, every section does.
EXPAND_ALL_MAX_KINDS = 14

#: Rows a section's table shows before it scrolls inside.
MAX_VISIBLE_KIND_ROWS = 12


class SettingsWindowState(HasTraits):
    """What the settings window remembers while the app runs."""

    #: The window's last size (px).
    size = Tuple(Int, Int, value=DEFAULT_WINDOW_SIZE)

    #: The tab last shown.
    tab_index = Int(0)

    #: Each "By kind" section the user expanded or collapsed, by group name;
    #: the others follow ``sections_expanded_at_first``.
    expanded = Dict(Str, Bool)


def fitted_window_size(size, available_height):
    """``size`` no smaller than MIN_WINDOW_SIZE and no taller than
    MAX_SCREEN_HEIGHT_FRACTION of ``available_height`` (px)."""
    width = max(size[0], MIN_WINDOW_SIZE[0])
    tallest = max(int(available_height * MAX_SCREEN_HEIGHT_FRACTION), 1)
    height = min(max(size[1], MIN_WINDOW_SIZE[1]), tallest)

    return width, height


def sections_expanded_at_first(kind_counts, most_kinds=EXPAND_ALL_MAX_KINDS):
    """Whether each section starts expanded, from its count of kinds: all
    of them when there are ``most_kinds`` kinds or fewer in all, else only
    the first."""

    if sum(kind_counts) <= most_kinds:
        return [True] * len(kind_counts)

    return [index == 0 for index in range(len(kind_counts))]


def kinds_summary(total, changed, shown=None):
    """A section header's summary: its count of kinds, or of those the
    filter shows (``shown``), and how many differ from their defaults."""
    plural = "kind" if total == 1 else "kinds"
    count = f"{total} {plural}" if shown is None else f"{shown} of {total} {plural}"

    return f"{count} · {changed} changed" if changed else count


def kind_matches(label, text):
    """Whether a kind named ``label`` passes the filter ``text``: every word
    of it found in the name, ignoring case."""
    name = label.casefold()

    return all(word in name for word in text.casefold().split())
