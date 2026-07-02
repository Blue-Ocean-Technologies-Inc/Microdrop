"""Run a slow blocking callable on a worker thread behind a modal, indeterminate
"please wait" dialog, marshalling the result back to the GUI thread.

Qt is allowed here (this is a UI helper, not a model). The worker callable must
NOT touch Qt or Traits models — only the on_success/on_error callbacks (which run
on the GUI thread) may."""
import threading

from pyface.api import GUI, ProgressDialog
from pyface.qt.QtCore import Qt

from logger.logger_service import get_logger

logger = get_logger(__name__)


def run_with_wait(work, *, title="Please wait", message="Working…",
                  on_success=None, on_error=None):
    """Show an indeterminate ProgressDialog, run ``work()`` on a worker thread,
    then (on the GUI thread) close the dialog and call ``on_success(result)`` or
    ``on_error(exc)``. Non-cancellable."""
    dialog = ProgressDialog(title=title, message=message, can_cancel=False)
    dialog.open()
    dialog.change_message(message)

    # Raise the dialog to the front so it isn't hidden behind the app window
    # (it has no parent, so Qt won't stack it above the main window for us),
    # and make it application-modal so the rest of the UI is blocked while the
    # worker runs. The event loop keeps running, so the worker callback and the
    # dialog still update — only user input to other windows is blocked.
    control = dialog.control
    if control is not None:
        control.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        control.setWindowModality(Qt.ApplicationModal)
        control.show()
        control.raise_()
        control.activateWindow()

    def _finish(success, payload):
        try:
            dialog.close()
        except Exception:
            pass
        if success:
            if on_success is not None:
                on_success(payload)
        else:
            logger.exception("threaded work failed", exc_info=payload)
            if on_error is not None:
                on_error(payload)

    def _worker():
        try:
            result = work()
        except Exception as e:                       # marshal failure to GUI thread
            GUI.invoke_later(_finish, False, e)
        else:
            GUI.invoke_later(_finish, True, result)

    threading.Thread(target=_worker, daemon=True).start()
