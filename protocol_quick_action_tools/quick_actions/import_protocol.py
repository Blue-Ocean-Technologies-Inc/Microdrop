"""'Import protocol into selected group' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_IMPORT_PROTOCOL
from .base import is_single_group_selected


class _ImportProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.import_into_selected_group()

    def is_enabled(self, ctx) -> bool:
        return (not ctx.is_running) and is_single_group_selected(ctx)


def make_import_protocol_action() -> _ImportProtocolAction:
    return _ImportProtocolAction(
        action_id=ACTION_IMPORT_PROTOCOL,
        icon_text="unarchive",
        tooltip="Import protocol into selected group",
        priority=40,
    )
