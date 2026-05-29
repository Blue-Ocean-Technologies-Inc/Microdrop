"""'Browse session reports' quick-action factory. Bound to 'R'."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_BROWSE_REPORTS


class _BrowseReportsAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.browse_reports_dialog()

    def is_enabled(self, ctx) -> bool:
        return ((not ctx.is_running)
                and getattr(ctx.pane, "experiment_manager", None) is not None)


def make_browse_reports_action() -> _BrowseReportsAction:
    return _BrowseReportsAction(
        action_id=ACTION_BROWSE_REPORTS,
        icon_text="summarize",
        tooltip="Browse session reports (R)",
        priority=80,
        shortcut="R",
    )
