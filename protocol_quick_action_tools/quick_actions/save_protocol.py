"""'Save Protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_SAVE_PROTOCOL


class _SaveProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.save_protocol_dialog()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_save_protocol_action() -> _SaveProtocolAction:
    return _SaveProtocolAction(
        action_id=ACTION_SAVE_PROTOCOL,
        icon_text="save",
        tooltip="Save Protocol",
        priority=60,
    )
