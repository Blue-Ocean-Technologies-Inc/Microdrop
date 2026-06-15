"""Logging lifecycle handler.

Drives ProtocolLoggingController start/stop from the executor's once-per-run
hooks instead of the protocol tree pane. Logging spans the whole run (all
repetitions): start_logging once in on_pre_protocol_start (right after the
RealtimeModeHandler turns realtime mode on, before steps run) and
stop_logging once in on_post_protocol_end.

The controller itself stays owned by the pane — it carries GUI collaborators
(report-flush progress dialog, completion callback). This handler only
triggers it at the right execution points. stop_logging kicks off the
report flush (a GUI progress dialog), so it's marshalled onto the GUI thread
via ctx.prompt_gui; start_logging is GUI-free and runs on the worker.
"""

from traits.api import Any, Callable

from pluggable_protocol_tree.models.column import BaseColumnHandler
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext

from logger.logger_service import get_logger
logger = get_logger(__name__)


class LoggingHandler(BaseColumnHandler):
    """Starts/stops protocol logging once per run."""

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

    def on_post_protocol_end(self, ctx):
        # stop_logging schedules the report flush behind a GUI progress
        # dialog — marshal it onto the GUI thread.
        try:
            ctx.prompt_gui(self.controller.stop_logging)
        except Exception as e:
            logger.warning(f"could not stop protocol logging: {e}")
