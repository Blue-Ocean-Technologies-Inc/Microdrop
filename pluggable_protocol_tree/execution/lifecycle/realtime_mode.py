"""Realtime-mode lifecycle handler.

Owns the pre-run realtime-mode handling that used to live in the protocol
tree pane (``_prepare_realtime_mode`` + the post-run restore):

  - realtime mode OFF before the run: turn it on, and turn it back off at
    the end (restore = False).
  - realtime mode ON, prompt enabled: ask whether to keep it after the run;
    the "don't ask again" checkbox persists the answer to preferences.
  - realtime mode ON, prompt disabled: follow the saved
    keep_realtime_mode_after_protocol preference.

Runs as an executor lifecycle handler (no column) at a high priority so it
trails every real column's on_protocol_start, and uses the once-per-run
on_pre_protocol_start / on_post_protocol_end hooks so the prompt + settle
happen once per run rather than once per repetition.
"""

import time

from pluggable_protocol_tree.models.column import BaseColumnHandler
from pluggable_protocol_tree.execution.exceptions import AbortError
from pluggable_protocol_tree.services.preferences import ProtocolPreferences

from dropbot_controller.consts import REALTIME_MODE_KEY, SET_REALTIME_MODE
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
logger = get_logger(__name__)

app_globals = get_microdrop_redis_globals_manager()

# Scratch key carrying the keep-realtime-after-run decision from
# on_pre_protocol_start to on_post_protocol_end (one ProtocolContext spans
# the whole run now that repeats live in the executor).
_RESTORE_REALTIME_SCRATCH_KEY = "pluggable_protocol_tree.keep_realtime_after_run"


class RealtimeModeHandler(BaseColumnHandler):
    """Turns realtime mode on before a run and restores it afterward."""

    priority = 900  # after every real column's start hooks

    def on_pre_protocol_start(self, ctx):
        if ctx.preview_mode:
            # Preview runs never touch hardware — no realtime-mode prep.
            return

        prefs = ProtocolPreferences()
        try:
            realtime_on = bool(app_globals.get(REALTIME_MODE_KEY, False))
        except Exception as e:
            logger.debug(f"realtime-mode state unavailable: {e}")
            realtime_on = False

        if not realtime_on:
            logger.info("Realtime mode off before protocol start; turning it on...")
            try:
                publish_message(topic=SET_REALTIME_MODE, message=str(True))
            except Exception as e:
                logger.warning(f"could not enable realtime mode: {e}")
            keep = False
        elif prefs.prompt_to_restore_realtime_mode:
            result = ctx.prompt_gui(self._ask_keep_realtime)
            if result is None:
                # Wait ended without an answer (e.g. external resume) —
                # fall back to the saved preference.
                keep = prefs.keep_realtime_mode_after_protocol
            else:
                user_choice, remember = result
                keep = user_choice == YES
                if remember:
                    prefs.prompt_to_restore_realtime_mode = False
                    prefs.keep_realtime_mode_after_protocol = keep
        else:
            keep = prefs.keep_realtime_mode_after_protocol
            logger.info(f"Realtime mode post-protocol (per preference): "
                        f"{'keep' if keep else 'disable'}")

        ctx.scratch[_RESTORE_REALTIME_SCRATCH_KEY] = keep

        # Let the hardware settle before the first step. Stop-aware so a
        # Stop during the settle aborts the run instead of stalling it.
        self._settle(ctx, float(prefs.realtime_mode_settling_time_s))

    def on_post_protocol_end(self, ctx):
        # If on_pre_protocol_start never ran — preview, or the run was
        # cancelled by an earlier pre hook (e.g. the recording dialog) before
        # this handler's bucket — there's no prep to restore.
        if _RESTORE_REALTIME_SCRATCH_KEY not in ctx.scratch:
            return
        if not ctx.scratch[_RESTORE_REALTIME_SCRATCH_KEY]:
            try:
                publish_message(topic=SET_REALTIME_MODE, message=str(False))
            except Exception as e:
                logger.warning(f"realtime-mode restore failed: {e}")

    @staticmethod
    def _ask_keep_realtime():
        """Runs on the GUI thread via ctx.prompt_gui. Returns (result, remember)."""
        return confirm(
            None,
            title="Keep Realtime Mode Enabled Post-Protocol?",
            message="<b>Realtime mode is currently ON.</b><br><br>"
                    "Would you like to keep it enabled after the "
                    "protocol finishes?",
            cancel=False,
            checkbox_text="Don't ask again (can be changed in preferences)",
        )

    @staticmethod
    def _settle(ctx, seconds):
        """Block the worker for ``seconds``, raising AbortError if stopped."""
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if ctx.stop_event.is_set():
                raise AbortError("stop_event fired during realtime settle")
            time.sleep(min(0.05, remaining))
