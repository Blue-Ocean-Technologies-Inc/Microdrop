"""
Camera Pre-warm Scheduler
=========================

Encapsulates the logic for pre-warming the camera video feed before steps
that require video, image capture, or recording.

At protocol start, the entire run order is scanned to build a timeline of
camera on/off transition events. These events are scheduled via APScheduler's
BackgroundScheduler using one-shot DateTrigger jobs, with "on" events shifted
back by a configurable pre-warm window (default 10 seconds).

The scheduler supports pause/resume with time-offset correction to keep the
schedule aligned with the protocol execution.

Usage (from ProtocolRunnerController):
    scheduler = CameraPrewarmScheduler(prewarm_seconds=10.0)
    scheduler.compile_and_start(run_order)
    ...
    scheduler.pause()
    scheduler.resume(pause_duration_seconds)
    ...
    scheduler.shutdown()
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.schedulers.base import STATE_RUNNING, STATE_PAUSED

from logger.logger_service import get_logger

logger = get_logger(__name__)

# Silence APScheduler executor noise
get_logger("apscheduler.executors.default").setLevel(level="WARNING")


def _is_checkbox_checked(item_or_value) -> bool:
    """Check whether a protocol parameter value represents a checked state."""
    if item_or_value is None:
        return False
    if isinstance(item_or_value, str):
        return item_or_value == "1"
    elif isinstance(item_or_value, bool):
        return item_or_value
    elif isinstance(item_or_value, int):
        return item_or_value == 1
    else:
        try:
            return str(item_or_value) == "1"
        except Exception:
            return False


class CameraPrewarmScheduler:
    """
    Pre-compiled camera video schedule that fires ``on_camera_on`` / ``on_camera_off``
    callbacks at the right wall-clock times during a protocol run.

    Parameters
    ----------
    prewarm_seconds : float
        How many seconds *before* a camera-needing step to turn the camera on.
    on_camera_on : callable
        Called (from a background thread) when the camera should turn ON.
    on_camera_off : callable
        Called (from a background thread) when the camera should turn OFF.
    calculate_step_time : callable
        ``(step, device_state) -> float`` — returns the expected duration
        (in seconds) for a single step.
    get_empty_device_state : callable
        Returns a fallback device state when a step has none.
    """

    def __init__(
        self,
        *,
        prewarm_seconds: float = 10.0,
        on_camera_on: Callable,
        on_camera_off: Callable,
        calculate_step_time: Callable,
        get_empty_device_state: Callable,
    ):
        self._prewarm_seconds = prewarm_seconds
        self._on_camera_on = on_camera_on
        self._on_camera_off = on_camera_off
        self._calculate_step_time = calculate_step_time
        self._get_empty_device_state = get_empty_device_state

        # Internal state
        self._scheduler: Optional[BackgroundScheduler] = None
        self._schedule: List[Tuple[float, str]] = []  # [(offset_s, "on"/"off"), ...]
        self._start_time: Optional[datetime] = None
        self._total_pause_duration: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def schedule(self) -> List[Tuple[float, str]]:
        """Return the compiled schedule for inspection / logging."""
        return list(self._schedule)

    def compile_and_start(self, run_order: list) -> None:
        """
        Scan *run_order*, build a camera on/off timeline, and start the
        background scheduler.

        Parameters
        ----------
        run_order : list[dict]
            The flattened protocol run order as produced by
            ``flatten_protocol_for_run``.  Each entry has a ``"step"`` key
            whose value is a protocol step with ``.parameters`` and
            ``.device_state``.
        """
        self.shutdown()  # clean up any previous run

        self._schedule = []
        self._total_pause_duration = 0.0

        # 1. Build a timeline: (cumulative_start, needs_camera, duration)
        cumulative_time = 0.0
        step_timeline: List[Tuple[float, bool, float]] = []

        for entry in run_order:
            step = entry["step"]
            device_state = (
                step.device_state
                if hasattr(step, "device_state") and step.device_state
                else None
            )
            if not device_state:
                device_state = self._get_empty_device_state()

            duration = self._calculate_step_time(step, device_state)

            video = _is_checkbox_checked(step.parameters.get("Video", "0"))
            capture = _is_checkbox_checked(step.parameters.get("Capture", "0"))
            record = _is_checkbox_checked(step.parameters.get("Record", ""))
            needs_camera = video or capture or record

            step_timeline.append((cumulative_time, needs_camera, duration))
            cumulative_time += duration

        # 2. Identify OFF→ON and ON→OFF transition edges
        camera_on = False
        for start_time, needs_camera, _duration in step_timeline:
            if needs_camera and not camera_on:
                on_time = max(0.0, start_time - self._prewarm_seconds)
                self._schedule.append((on_time, "on"))
                camera_on = True
            elif not needs_camera and camera_on:
                self._schedule.append((start_time, "off"))
                camera_on = False
        # If the protocol ends with camera still on, _on_protocol_finished in
        # the controller will handle the final OFF.

        if not self._schedule:
            logger.info("Camera schedule: no camera events needed for this protocol.")
            return

        # 3. Create scheduler and submit jobs
        self._start_time = datetime.now()
        self._scheduler = BackgroundScheduler()

        for idx, (offset_s, action) in enumerate(self._schedule):
            self._add_job(idx, offset_s, action, suffix="")

        self._scheduler.start()
        logger.info(f"Camera scheduler started with {len(self._schedule)} event(s).")

    def pause(self) -> None:
        """Pause all pending camera events (call when protocol is paused)."""
        if self._scheduler is None:
            return
        try:
            if self._scheduler.state == STATE_RUNNING:
                self._scheduler.pause()
                logger.info("Camera scheduler paused.")
        except Exception as e:
            logger.error(f"Error pausing camera scheduler: {e}")

    def resume(self, pause_duration_seconds: float) -> None:
        """
        Resume after a pause, rescheduling remaining events to account for
        the time the protocol was paused.
        """
        if self._scheduler is None or self._start_time is None:
            return

        try:
            self._total_pause_duration += pause_duration_seconds

            # Remove all pending jobs — we will re-add the ones that haven't
            # fired yet with corrected times.
            for job in self._scheduler.get_jobs():
                self._scheduler.remove_job(job.id)

            elapsed = (
                datetime.now() - self._start_time
            ).total_seconds() - self._total_pause_duration

            jobs_added = 0
            for idx, (offset_s, action) in enumerate(self._schedule):
                if offset_s < elapsed:
                    continue  # already fired

                delay = offset_s - elapsed
                run_date = datetime.now() + timedelta(seconds=delay)
                callback = self._on_camera_on if action == "on" else self._on_camera_off
                self._scheduler.add_job(
                    func=callback,
                    trigger=DateTrigger(run_date=run_date),
                    id=f"camera_{action}_{idx}_resumed",
                    replace_existing=True,
                    misfire_grace_time=None,
                )
                jobs_added += 1
                logger.debug(
                    f"Camera schedule resumed: {action.upper()} in {delay:.1f}s"
                )

            if self._scheduler.state == STATE_PAUSED:
                self._scheduler.resume()

            logger.info(
                f"Camera scheduler resumed with {jobs_added} remaining event(s) "
                f"(pause was {pause_duration_seconds:.1f}s)."
            )
        except Exception as e:
            logger.error(f"Error resuming camera scheduler: {e}")

    def shutdown(self) -> None:
        """Shut down the scheduler and release all resources."""
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
                logger.info("Camera scheduler shut down.")
            except Exception as e:
                logger.error(f"Error shutting down camera scheduler: {e}")
            finally:
                self._scheduler = None

        self._schedule = []
        self._start_time = None
        self._total_pause_duration = 0.0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_job(self, idx: int, offset_s: float, action: str, suffix: str) -> None:
        """Add a single DateTrigger job to the scheduler."""
        run_date = self._start_time + timedelta(seconds=offset_s)
        callback = self._on_camera_on if action == "on" else self._on_camera_off

        self._scheduler.add_job(
            func=callback,
            trigger=DateTrigger(run_date=run_date),
            id=f"camera_{action}_{idx}{suffix}",
            replace_existing=True,
            misfire_grace_time=None,  # always fire even if late
        )
        logger.info(
            f"Camera schedule: {action.upper()} at T+{offset_s:.1f}s "
            f"(abs: {run_date.strftime('%H:%M:%S.%f')})"
        )
