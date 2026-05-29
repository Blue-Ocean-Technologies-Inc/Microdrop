"""'Delete selected step / group' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_DELETE_ROW
from .base import has_selection


class _DeleteRowAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.delete_selected_rows()

    def is_enabled(self, ctx) -> bool:
        return (not ctx.is_running) and has_selection(ctx)


def make_delete_row_action() -> _DeleteRowAction:
    return _DeleteRowAction(
        action_id=ACTION_DELETE_ROW,
        icon_text="delete",
        tooltip="Delete selected step / group",
        priority=20,
    )
