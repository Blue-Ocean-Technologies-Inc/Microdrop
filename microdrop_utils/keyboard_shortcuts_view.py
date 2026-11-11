# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The keyboard shortcut cheat sheet: a non-modal window per shortcut table."""

# Standard library imports.
from html import escape

# Enthought library imports.
from traits.api import HasTraits, Str
from traitsui.api import HTMLEditor, Item, View

# Local imports.
from .keyboard_shortcuts import cheat_sheet_rows

# The open cheat sheets' UIs by window title, held here so they are not
# garbage-collected while their non-modal windows are open.
_open_sheet_uis = {}


def cheat_sheet_html(table, groups):
    """Return the cheat sheet: a heading and a key table per group."""
    sections = []

    for group, rows in cheat_sheet_rows(table, groups):
        table_rows = "".join(
            f"<tr><td><kbd>{escape(keys)}</kbd></td><td>{escape(text)}</td></tr>"
            for keys, text in rows
        )
        sections.append(f"<h3>{escape(group)}</h3><table>{table_rows}</table>")

    return "".join(sections)


class KeyboardShortcutsSheet(HasTraits):
    """A shortcut table, laid out for reading."""

    #: The cheat sheet as HTML.
    html = Str()


def keyboard_shortcuts_view(title):
    """Return the cheat sheet window's view, titled ``title``."""
    return View(
        Item("html", editor=HTMLEditor(), show_label=False),
        title=title,
        width=420,
        height=520,
        resizable=True,
        buttons=["OK"],
    )


def show_keyboard_shortcuts(table, groups, title):
    """Open the cheat sheet non-modally, or raise it if it is already open.

    One window per ``title``, so each plugin's sheet opens beside the
    others rather than replacing them.
    """
    open_ui = _open_sheet_uis.get(title)

    if open_ui is not None and open_ui.control is not None:
        open_ui.control.raise_()
        open_ui.control.activateWindow()

        return

    sheet = KeyboardShortcutsSheet(html=cheat_sheet_html(table, groups))
    _open_sheet_uis[title] = sheet.edit_traits(view=keyboard_shortcuts_view(title))
