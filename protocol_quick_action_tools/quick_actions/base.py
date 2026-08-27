# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Shared helpers used by every action factory.

Keeps the per-action factory files (one per file) one-purpose: build
an IQuickAction with the right id / icon / tooltip / hooks. Predicates
that several actions share (``has_selection``, ``is_single_group_selected``,
...) live here.
"""

from pluggable_protocol_tree.models.row import GroupRow


def has_selection(ctx) -> bool:
    return len(ctx.selected_paths) >= 1


def is_single_row_selected(ctx) -> bool:
    return len(ctx.selected_paths) == 1


def is_single_group_selected(ctx) -> bool:
    """True iff exactly one row is selected AND that row is a GroupRow."""
    if not is_single_row_selected(ctx):
        return False
    pane = ctx.pane
    try:
        row = pane.manager.get_row(tuple(ctx.selected_paths[0]))
    except (IndexError, AttributeError):
        return False
    return isinstance(row, GroupRow)
