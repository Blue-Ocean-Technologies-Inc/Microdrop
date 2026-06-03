"""Per-step user message-prompt column.

Stores a free-text message on each row (Str trait). When a step carries a
non-empty message, the handler pauses the protocol at the *start* of that
step (``on_pre_step``) and shows a modal confirm dialog with the message
and two choices, "Continue" and "Stay Paused". The protocol stays paused —
its step/phase timers frozen via ``protocol_paused`` — until the operator
picks Continue, then resumes. Choosing Stay Paused (or dismissing the
dialog) leaves the step parked; from there the run can only be cleared with
the toolbar Stop. An empty message is a no-op, so the column is free on
steps that don't need an operator gate.

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

        No-op when the step has no message. Otherwise the worker thread
        parks until the operator picks Continue (resume) or the run is
        stopped; the step/phase timers stay frozen while parked.
        """
        val = row.message_prompt
        qsignals = ctx.protocol.qsignals

        if val:
            self._wait_for_dialog_event.clear()

            def _user_prompt():
                # Runs on the GUI thread (see module docstring). The worker
                # thread is parked in ctx.wait below; only "Continue" sets
                # the dialog event and releases it. "Stay Paused" (or any
                # dismissal, which confirm() reports as NO/CANCEL) leaves the
                # step parked until the toolbar Stop trips stop_event.
                usr_choice = confirm(
                    None,
                    message=val,
                    yes_label="Continue",
                    no_label="Stay Paused",
                    title="Message Prompt",
                )

                if usr_choice == YES:
                    logger.info("Message prompt: operator chose Continue; resuming")
                    self._wait_for_dialog_event.set()
                else:
                    logger.info("Message prompt: operator left the step paused "
                                f"(choice={usr_choice})")

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
