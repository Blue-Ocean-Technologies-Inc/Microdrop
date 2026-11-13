# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The shortcuts tutorial's finder table against the shortcut tables in code.

Rows marked ``data-source`` copy a table word for word; these tests fail
when a key or its wording changes in code but not on the page.
"""

# Standard library imports.
import os
from html.parser import HTMLParser

# Qt reads the platform when the first QApplication is made, which importing
# the plugins below can do; set it first so no test ever opens a window.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Microdrop package imports.
from device_viewer.consts import KEYBOARD_SHORTCUT_GROUPS as DEVICE_VIEWER_GROUPS
from device_viewer.consts import KEYBOARD_SHORTCUTS as DEVICE_VIEWER_SHORTCUTS
from image_viewer.consts import KEYBOARD_SHORTCUT_GROUPS as IMAGE_VIEWER_GROUPS
from image_viewer.consts import KEYBOARD_SHORTCUTS as IMAGE_VIEWER_SHORTCUTS
from microdrop_application.consts import SHORTCUTS_TUTORIAL_HTML_PATH
from pluggable_protocol_tree.consts import (
    PROTOCOL_REDO_SHORTCUTS,
    PROTOCOL_UNDO_SHORTCUT,
    STEP_PATTERN_SHORTCUT,
)
from protocol_quick_action_tools.plugin import ProtocolQuickActionToolsPlugin

# Microdrop utils imports.
from microdrop_utils.keyboard_shortcuts import primary_action

SOURCE_PATH = SHORTCUTS_TUTORIAL_HTML_PATH.with_name("shortcuts.src.html")

#: How the page separates two keys for one action, as the cheat sheet does.
KEY_SEPARATOR = " / "


class _FinderRows(HTMLParser):
    """Collect ``(source, keys, what, where)`` for every finder row that has
    a ``data-source``, in page order."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self._source = None
        self._cell = None
        self._cells = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "tr" and "data-source" in attrs:
            self._source = attrs["data-source"]
            self._cells = {}

        elif tag == "td" and self._source is not None:
            self._cell = attrs.get("class")
            self._cells[self._cell] = ""

    def handle_endtag(self, tag):
        if tag == "td":
            self._cell = None

        elif tag == "tr" and self._source is not None:
            cells = self._cells
            keys = tuple(cells["keys"].split(KEY_SEPARATOR))
            self.rows.append((self._source, keys, cells["what"], cells["where"]))
            self._source = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cells[self._cell] += data


def _page_rows(source):
    parser = _FinderRows()
    parser.feed(SOURCE_PATH.read_text(encoding="utf-8"))

    return [row[1:] for row in parser.rows if row[0] == source]


def _cheat_sheet(table, groups):
    """Fold a shortcut table like the in-app cheat sheet: one row per action,
    its keys in table order, the rows grouped in ``groups`` order."""
    keys_by_action = {}
    rows_by_group = {group: [] for group in groups}

    for sequence, action, description, group in table:
        primary = primary_action(action)

        if primary in keys_by_action:
            keys_by_action[primary].append(sequence)
            continue

        keys_by_action[primary] = [sequence]
        rows_by_group[group].append((primary, description))

    return [
        (tuple(keys_by_action[action]), description, group)
        for group in groups
        for action, description in rows_by_group[group]
    ]


def test_device_viewer_rows_match_the_shortcut_table():
    page = [(keys, what, where) for keys, what, where in _page_rows("device_viewer")]
    expected = [
        (keys, description, f"Device Viewer · {group}")
        for keys, description, group in _cheat_sheet(
            DEVICE_VIEWER_SHORTCUTS, DEVICE_VIEWER_GROUPS
        )
    ]

    assert page == expected


def test_image_viewer_rows_match_the_shortcut_table():
    page = [(keys, what, where) for keys, what, where in _page_rows("image_viewer")]
    expected = [
        (keys, description, f"Image Viewer · {group}")
        for keys, description, group in _cheat_sheet(
            IMAGE_VIEWER_SHORTCUTS, IMAGE_VIEWER_GROUPS
        )
    ]

    assert page == expected


def test_quick_action_rows_match_the_quick_actions():
    actions = ProtocolQuickActionToolsPlugin()._contributed_quick_actions_default()
    expected = [
        ((action.shortcut,), action.tooltip.removesuffix(f" ({action.shortcut})"))
        for action in actions
        if action.shortcut
    ]

    page = [(keys, what) for keys, what, _ in _page_rows("quick_actions")]

    assert page == expected


def test_protocol_history_rows_match_the_history_keys():
    keys = [keys for keys, _, _ in _page_rows("protocol_history")]

    assert keys == [(PROTOCOL_UNDO_SHORTCUT,), tuple(PROTOCOL_REDO_SHORTCUTS)]


def test_fill_pattern_row_matches_its_key():
    keys = [keys for keys, _, _ in _page_rows("step_pattern")]

    assert keys == [(STEP_PATTERN_SHORTCUT,)]
