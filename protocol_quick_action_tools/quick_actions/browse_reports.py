"""'Browse session reports' quick-action factory. Bound to 'R'."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_BROWSE_REPORTS
from ..views.report_browser_dialog import ReportBrowserDialog


class _BrowseReportsAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        self._open_dialog(ctx.pane)

    def is_enabled(self, ctx) -> bool:
        return ((not ctx.is_running)
                and getattr(ctx.pane, "experiment_manager", None) is not None)

    @staticmethod
    def _open_dialog(pane):
        """Open the ReportBrowserDialog over the session's
        accumulated report paths (tracked by
        ProtocolLoggingController.all_report_paths across every run
        since app start)."""
        paths = [
            str(p) for p in
            (getattr(pane.logging_controller, "all_report_paths", None) or [])
        ]
        ReportBrowserDialog(paths, parent=pane).exec()


def make_browse_reports_action() -> _BrowseReportsAction:
    return _BrowseReportsAction(
        action_id=ACTION_BROWSE_REPORTS,
        icon_text="summarize",
        tooltip="Browse session reports (R)",
        priority=80,
        shortcut="R",
    )
