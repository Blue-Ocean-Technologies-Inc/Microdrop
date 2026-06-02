"""Per-step user message-prompt column.

Stores a free-text message on each row (Str trait). When a step carries a
non-empty message, the handler pauses the protocol at the *start* of that
step (``on_pre_step``) and shows a modal confirm dialog with the message.
The protocol stays paused — its step/phase timers frozen via
``protocol_paused`` — until the operator acknowledges the dialog, then
resumes. An empty message is a no-op, so the column is free on steps that
don't need an operator gate.

This mirrors the legacy ``user_prompt_plugin`` "message" step setting: a
manual checkpoint the operator must clear before the run continues (e.g.
"Load 100uL", "Place chip", "Inspect droplet").

Threading: the handler runs on the executor's worker thread, but Qt
dialogs must be created on the GUI thread. The confirm() call is therefore
marshaled onto the GUI thread with ``QTimer.singleShot`` (passing the
qsignals QObject as the timer's context so the callback runs in that
object's — i.e. the GUI — thread), while the worker thread blocks in
``ctx.wait`` on a ``threading.Event`` the dialog callback sets. Priority
is the default (50); ordering relative to other on_pre_step hooks doesn't
matter because the prompt gates the whole step.
"""

import threading

from PySide6.QtCore import QTimer
from traits.api import Str

from logger.logger_service import get_logger
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
from pluggable_protocol_tree.execution.exceptions import AbortError
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.string_edit import StringEditColumnView

logger = get_logger(__name__)


class MsgPromptColumnModel(BaseColumnModel):
    """Free-text message shown to the operator when the step starts.

    Empty string (the default) means "no prompt" — the handler skips the
    pause entirely.
    """

    def trait_for_row(self):
        return Str()


class MsgPromptColumnHandler(BaseColumnHandler):
    """Pauses the protocol and prompts the operator at step start.

    Holds a single reusable ``_wait_for_dialog_event`` (one handler
    instance is shared across all steps, since execution is serial) that
    the dialog callback sets once the operator acknowledges.
    """

    def traits_init(self):
        # Reused across steps; cleared at the start of every prompting
        # step before the dialog is shown.
        self._wait_for_dialog_event = threading.Event()

    def on_pre_step(self, row, ctx):
        """Block this step behind an operator-acknowledged dialog.

        No-op when the step has no message. Raises ``AbortError`` if the
        protocol was already stopped before the prompt is shown so a
        pending Stop isn't masked by the dialog.
        """
        val = row.message_prompt
        qsignals = ctx.protocol.qsignals

        if ctx.protocol.stop_event.is_set():
            raise AbortError("Protocol was stopped")

        if val:
            self._wait_for_dialog_event.clear()

            def _user_prompt():
                # Runs on the GUI thread (see module docstring). The
                # worker thread is parked in ctx.wait below until this
                # sets the dialog event.
                usr_choice = confirm(
                    None,
                    message=val,
                    title="Message Prompt",
                )

                if usr_choice == YES:
                    logger.info("User selected message prompt yes")
                    self._wait_for_dialog_event.set()
                else:
                    logger.info(f"User selected message prompt {usr_choice}")

            QTimer.singleShot(0, qsignals, _user_prompt)
            # Park the worker thread until the operator acknowledges
            # (event set) or the run is stopped (stop_event).
            ctx.wait(events=[self._wait_for_dialog_event, ctx.protocol.stop_event])


def make_message_prompt_column():
    return Column(
        model=MsgPromptColumnModel(
            col_id="message_prompt", col_name="Message", default_value="",
        ),
        handler=MsgPromptColumnHandler(),
        view=StringEditColumnView(),
    )
