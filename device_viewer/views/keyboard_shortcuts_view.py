# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from html import escape

# Enthought library imports.
from traits.api import HasTraits, Str
from traitsui.api import HTMLEditor, Item, View

# Local imports.
from ..services.keyboard_shortcut_service import cheat_sheet_rows

# The open cheat sheet's UI, held here so it is not garbage-collected while
# its non-modal window is open.
_open_sheet_ui = None


def _cheat_sheet_html():
    """Return the cheat sheet: a heading and a key table per group."""
    sections = []

    for group, rows in cheat_sheet_rows():
        table_rows = "".join(
            f"<tr><td><kbd>{escape(keys)}</kbd></td><td>{escape(text)}</td></tr>"
            for keys, text in rows
        )
        sections.append(f"<h3>{escape(group)}</h3><table>{table_rows}</table>")

    return "".join(sections)


class KeyboardShortcutsSheet(HasTraits):
    """The device view's keyboard shortcuts, laid out for reading."""

    #: The cheat sheet as HTML, built from KEYBOARD_SHORTCUTS.
    html = Str()

    def _html_default(self):
        return _cheat_sheet_html()


keyboard_shortcuts_view = View(
    Item("html", editor=HTMLEditor(), show_label=False),
    title="Keyboard Shortcuts",
    width=420,
    height=520,
    resizable=True,
    buttons=["OK"],
)


def show_keyboard_shortcuts():
    """Open the cheat sheet non-modally, or raise it if it is already open."""
    global _open_sheet_ui

    if _open_sheet_ui is not None and _open_sheet_ui.control is not None:
        _open_sheet_ui.control.raise_()
        _open_sheet_ui.control.activateWindow()

        return

    _open_sheet_ui = KeyboardShortcutsSheet().edit_traits(view=keyboard_shortcuts_view)
