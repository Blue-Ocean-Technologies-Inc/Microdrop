"""Dialog-aware decorators.

Lives in the dialogs package (not microdrop_utils) because these
decorators surface errors through the styled dialog system — keeping
them here keeps microdrop_utils Qt-free for service/model-layer
consumers.
"""

import functools
import html

from microdrop_application.dialogs.pyface_wrapper import (
    error, escape_html_multiline, format_traceback_detail,
)
from microdrop_style.colors import DIALOG_ERROR_TEXT_COLOR
from logger.logger_service import get_logger

logger = get_logger(__name__)


def attempt_func_execution_with_error_dialog(func):
    """Wrap a QWidget instance method so any uncaught exception is surfaced
    to the user as a styled error dialog instead of crashing the widget.

    The dialog uses the pyface_wrapper.error layout:
      * ``message``    — one-line summary: humanised operation name +
                         exception type. Plain text.
      * ``informative`` — HTML body: bold op name + red exception type +
                          escaped exception message.
      * ``detail``     — full traceback, collapsible preformatted.

    Also logs the exception with full traceback so the error is captured
    even when the user dismisses the dialog.

    Intended for top-level user-triggered UI actions (file open / save /
    import / browse-reports / etc.). Do NOT use on executor callbacks —
    those handle errors via the executor's own signal chain.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as exc:
            op_name = func.__name__.replace("_", " ").strip().title()
            logger.error(f"{op_name} failed: {exc}", exc_info=True)
            detail = format_traceback_detail(exc)
            cause = escape_html_multiline(str(exc) or "(no message)")
            informative = (
                f"<p style='margin:0 0 6px 0;'>"
                f"<b>{html.escape(op_name)}</b> failed.</p>"
                f"<p style='margin:0;color:{DIALOG_ERROR_TEXT_COLOR};'>"
                f"<b>{html.escape(type(exc).__name__)}:</b> {cause}</p>"
            )
            try:
                error(
                    self,
                    message=f"{op_name} failed: {type(exc).__name__}",
                    title=f"{op_name} Error",
                    informative=informative,
                    detail=detail,
                )
            except Exception as dialog_err:
                logger.error(
                    f"failed to show error dialog for {op_name}: "
                    f"{dialog_err}", exc_info=True)
            return None
    return wrapper
