"""Handler for the launch update-check dialog: Update All runs the bulk
update on a worker thread and then offers the standard relaunch popup;
Later just closes.

Worker callables (do_update_all) must not touch model traits — they return
data and the GUI-thread callbacks act on it (project threading rule)."""
from traits.api import Any
from traitsui.api import Handler

from microdrop_application.dialogs.pyface_wrapper import (
    error as error_dialog, escape_html_multiline)
from microdrop_utils.threaded_progress import run_with_wait

from .relaunch import confirm_and_relaunch


def show_update_dialog(report, application):
    """Open the update dialog for a non-empty report. GUI thread only —
    schedule via ``GUI.invoke_later`` from workers."""
    from .update_model import UpdateDialogModel
    from .update_view import update_view

    window = getattr(application, "active_window", None)
    task = getattr(window, "active_task", None)
    model = UpdateDialogModel(report=report)
    model.edit_traits(view=update_view,
                      handler=UpdateDialogHandler(task=task))


class UpdateDialogHandler(Handler):
    """Runs the bulk update, reports failures, then offers a relaunch."""

    #: The active task, for confirm_and_relaunch (None-safe: the helper
    #: degrades gracefully without a running application).
    task = Any(None)

    def update_all(self, info):
        model = info.object
        run_with_wait(
            model.do_update_all,
            title="Updating plugins", message="Updating plugins…",
            on_success=lambda result: self._after_update(info, result),
            on_error=lambda e: error_dialog(
                parent=None, title="Update failed", message=str(e)),
        )

    def _after_update(self, info, result):
        succeeded, failed = result
        if failed:
            failures = "<br>".join(
                f"<b>{escape_html_multiline(name)}</b>: "
                f"{escape_html_multiline(err)}"
                for name, err in failed
            )
            error_dialog(parent=None, title="Some updates failed",
                         message=failures)
        info.ui.dispose()
        if succeeded:
            names = ", ".join(
                f"<b>{escape_html_multiline(name)}</b>" for name in succeeded
            )
            confirm_and_relaunch(self.task, f"Updated {names}.")

    def do_close(self, info):
        info.ui.dispose()
