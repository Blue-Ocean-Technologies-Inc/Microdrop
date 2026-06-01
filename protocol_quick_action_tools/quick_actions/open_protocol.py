"""'Open Protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_OPEN_PROTOCOL


class _OpenProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.load_protocol_dialog()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_open_protocol_action() -> _OpenProtocolAction:
    return _OpenProtocolAction(
        action_id=ACTION_OPEN_PROTOCOL,
        icon_text="file_open",
        tooltip="Open Protocol",
        priority=50,
    )
