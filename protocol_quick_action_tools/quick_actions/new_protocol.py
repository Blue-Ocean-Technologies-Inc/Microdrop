"""'New protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_NEW_PROTOCOL


class _NewProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.new_protocol()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_new_protocol_action() -> _NewProtocolAction:
    return _NewProtocolAction(
        action_id=ACTION_NEW_PROTOCOL,
        icon_text="new_window",
        tooltip="New protocol",
        priority=70,
        shortcut="Ctrl+N"
    )
