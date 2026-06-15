"""Logging lifecycle handler.

Starts ProtocolLoggingController logging from the executor's once-per-run
on_pre_protocol_start hook — right after the RealtimeModeHandler turns
realtime mode on, before any steps run, so one log spans the whole run
(all repetitions).

Only the *start* lives here. Stopping is left to the pane's end-of-run
completion flow: it is wrapped in genuine UX (protocol auto-save, the
"generate run summary?" / "start new experiment?" prompts, and the
generate_report decision) and, now that the executor owns the repeat loop,
that terminal flow already runs exactly once per run.

The controller stays owned by the pane (it carries GUI collaborators — the
report-flush progress dialog and completion callback); this handler only
triggers start_logging at the right execution point. start_logging is
GUI-free, so it runs on the executor's worker thread. Experiment directory
and step count come from injected providers.
"""

from traits.api import Any, Callable

from pluggable_protocol_tree.models.column import BaseColumnHandler
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext

from logger.logger_service import get_logger
logger = get_logger(__name__)


class LoggingHandler(BaseColumnHandler):
    """Starts protocol logging once per run, just before the first step."""

    priority = 1000  # after RealtimeModeHandler (900) — logger starts last

    #: The pane-owned ProtocolLoggingController.
    controller = Any
    #: () -> Path : the active experiment directory.
    experiment_dir_provider = Callable
    #: () -> int : number of execution frames (steps) per repetition.
    n_steps_provider = Callable

    def on_pre_protocol_start(self, ctx):
        try:
            device_ctx = LoggingDeviceContext(
                experiment_directory=self.experiment_dir_provider(),
            )
            n_steps = self.n_steps_provider()
            # start_logging no-ops in preview (ingestion stays None).
            self.controller.start_logging(device_ctx, n_steps, ctx.preview_mode)
        except Exception as e:
            logger.warning(f"could not start protocol logging: {e}")
