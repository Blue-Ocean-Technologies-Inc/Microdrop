"""'Delete last step' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_DELETE_ROW


class _DeleteRowAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.delete_last_step()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_delete_row_action() -> _DeleteRowAction:
    return _DeleteRowAction(
        action_id=ACTION_DELETE_ROW,
        icon_text="delete",
        tooltip="Delete last step",
        priority=20,
    )
