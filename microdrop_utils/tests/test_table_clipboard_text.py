# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The tab-separated text install_table_clipboard copies and pastes:
spreadsheet layout either way."""

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import parse_table_text, table_cells_text


def test_cells_are_laid_out_by_row_then_column_whatever_the_selection_order():
    cells = [(1, 1, "d"), (0, 1, "b"), (1, 0, "c"), (0, 0, "a")]

    assert table_cells_text(cells) == "a\tb\nc\td"


def test_a_row_keeps_only_its_selected_cells():
    cells = [(0, 0, "a"), (0, 2, "c"), (3, 1, "x")]

    assert table_cells_text(cells) == "a\tc\nx"


def test_a_spreadsheet_block_parses_without_its_trailing_newline():
    assert parse_table_text("a\tb\r\nc\t\n") == [["a", "b"], ["c", ""]]


def test_copied_text_parses_back_to_the_same_rows():
    cells = [(0, 0, "Point 1"), (0, 1, ""), (1, 0, "Point 2"), (1, 1, "65.4")]

    assert parse_table_text(table_cells_text(cells)) == [
        ["Point 1", ""],
        ["Point 2", "65.4"],
    ]


def test_empty_clipboard_has_no_rows():
    assert parse_table_text("") == []
