"""'Add step below selection' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_ADD_STEP


class _AddStepAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.add_step_after_selection()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_add_step_action() -> _AddStepAction:
    return _AddStepAction(
        action_id=ACTION_ADD_STEP,
        icon_text="add",
        tooltip="Add step below selection",
        priority=10,
    )
