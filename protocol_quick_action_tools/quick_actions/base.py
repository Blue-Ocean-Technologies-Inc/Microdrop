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
