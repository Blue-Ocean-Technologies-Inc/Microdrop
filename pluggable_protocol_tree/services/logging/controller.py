"""GUI-thread controller that turns executor lifecycle signals into a
run's worth of logged artifacts. Owns a LoggingIngestion per run; the
logging listener forwards capacitance/actuation/media to it. Settling
flush is deferred so in-flight capacitance after 'done' is captured.

Decoupled: communicates only via the listener (dramatiq) and the shared
Redis app_globals — it never imports another plugin's classes/panes. The
Qt-aware flush scheduler is injected by the view; the service default is
Qt-free."""

import json
import threading
from datetime import datetime, timedelta

from traits.api import Any, Bool, Callable, HasTraits, Instance, Int, List, Str

from device_viewer.consts import LIQUID_CAPACITANCE_KEY, FILLER_CAPACITANCE_KEY, MEDIA_CAPTURES_KEY
from device_viewer.models.media import MediaCaptureMessageModel
from logger.logger_service import get_logger
from microdrop_application.helpers import get_microdrop_redis_globals_manager

from pluggable_protocol_tree.consts import DEFAULT_LOGS_SETTLING_SECONDS
from pluggable_protocol_tree.services.logging import listener as _listener
from pluggable_protocol_tree.services.logging.consts import (
    RUN_TIMESTAMP_FMT, TIME_FMT,
)
from pluggable_protocol_tree.services.logging.ingestion import LoggingIngestion
from pluggable_protocol_tree.services.logging.persistence import LoggingPersistence
from pluggable_protocol_tree.services.logging.reporting import LoggingReport

logger = get_logger(__name__)

# Redis-backed shared state, bound once at import (the canonical idiom across
# the repo). The proxy connects lazily, so this is import-safe without Redis;
# the media-bucket reset/drain below wrap their access in try/except so the
# feature degrades gracefully when Redis is unreachable (tests/headless).
app_globals = get_microdrop_redis_globals_manager()


def _default_settling_provider() -> float:
    """Service-layer default settling delay (seconds). The view injects a
    provider reading ProtocolPreferences.logs_settling_time_s in the full
    app; this prefs-free default keeps the service layer decoupled."""
    return DEFAULT_LOGS_SETTLING_SECONDS


def _threading_flush_scheduler(controller) -> None:
    """Service-layer default flush scheduler: defer the flush by the settling
    delay on a plain timer — no Qt (the view injects a Qt/progress-aware
    scheduler in the full app)."""
    threading.Timer(controller.settling_provider(), controller._flush).start()


def _format_elapsed(delta: timedelta) -> str:
    """`H:MM:SS` for the metadata table (sub-second jitter is noise here)."""
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _capacitance_per_unit_area(liquid, filler):
    """liquid - filler (pF/mm^2), or None when invalid. Mirrors the legacy
    ForceCalculationService.calculate_capacitance_per_unit_area: both
    values must be present, non-negative, and liquid must exceed filler."""
    if liquid is None or filler is None:
        return None
    try:
        liquid = float(liquid)
        filler = float(filler)
    except (ValueError, TypeError):
        return None
    if liquid < 0 or filler < 0 or liquid <= filler:
        return None
    return liquid - filler


class ProtocolLoggingController(HasTraits):
    # Injected collaborators (constructor kwargs). settling_provider returns
    # the settling delay (s); flush_scheduler defers _flush; completion_callback
    # is notified with the report path (or None) after a flush.
    settling_provider = Callable
    flush_scheduler = Callable
    completion_callback = Callable          # Optional — None when not provided.
    # Optional — notified with the error message when a report the user asked
    # for could not be generated, so the failure isn't silent. None = not wired.
    report_failure_callback = Callable
    # Per-run state.
    _ingestion = Instance(LoggingIngestion)
    _device_context = Any
    _step_idx = Int(0)
    _n_steps = Int(0)
    _start_time = Str("")
    _start_dt = Instance(datetime)
    _generate_report = Bool(True)
    all_report_paths = List()

    def _settling_provider_default(self):
        return _default_settling_provider

    def _flush_scheduler_default(self):
        return _threading_flush_scheduler

    # --- executor signal wiring ---
    def attach(self, qsignals) -> None:
        # Only the per-step context comes from the executor signals.
        # start_logging / stop_logging are driven by the pane: a
        # whole-protocol repeat run restarts the executor per repetition
        # (firing protocol_finished each time), so the pane stops logging
        # once at its single terminal point — keeping all repeats in one
        # log instead of stopping after the first.
        qsignals.observe(self._on_step_started, "step_started")

    def has_data(self) -> bool:
        """True when the active run logged something worth reporting — i.e. at
        least one step started. A run stopped before any step ran (e.g. Stop on
        the loading screen) has nothing meaningful, so the report can be
        skipped. ``_step_idx`` counts step_started signals and survives
        abort/error."""
        return self._ingestion is not None and self._step_idx > 0

    def log_metadata(self, mapping: dict) -> None:
        """Forward extra report metadata to the active run's ingestion.
        No-op when no run is logging (e.g. preview, or after flush)."""
        ing = self._ingestion
        if ing is not None:
            ing.log_metadata(mapping)

    # --- lifecycle ---
    def start_logging(self, device_context, n_steps: int, preview_mode: bool) -> None:
        if preview_mode:
            self._ingestion = None
            return
        self._device_context = device_context
        self._ingestion = LoggingIngestion()
        self._ingestion.update_capacitance_per_unit_area(
            getattr(device_context, "capacitance_per_unit_area", None))
        self._step_idx = 0
        self._n_steps = int(n_steps)
        self._start_time = datetime.now().strftime(RUN_TIMESTAMP_FMT)
        self._start_dt = datetime.now()
        self._ingestion.log_metadata({
            "Experiment Directory": str(device_context.experiment_directory),
            "Device SVG": str(getattr(device_context, "device_svg_path", "")),
            "Steps": f"0 / {self._n_steps}",
        })
        # Reset the shared media-captures bucket so only THIS run's camera
        # output ends up in this run's report — _flush drains it back. The
        # camera capture path (device_viewer's _cache_media_capture actor)
        # appends serialised MediaCaptureMessageModel JSON to
        # app_globals[MEDIA_CAPTURES_KEY] but never publishes the
        # DEVICE_VIEWER_MEDIA_CAPTURED topic, so the listener can't see
        # captures live (legacy parity bug); reading the bucket at flush
        # time closes the gap.
        try:
            app_globals[MEDIA_CAPTURES_KEY] = []
        except Exception as e:                # pragma: no cover - defensive
            logger.debug(f"could not reset media_captures bucket: {e}")
        _listener.set_active_logger(self)

    def _on_step_started(self, event) -> None:
        if self._ingestion is None:
            return
        row, _step_index, _step_total = event.new
        self._step_idx += 1
        self._ingestion.set_step(step_id=getattr(row, "uuid", ""),
                                 step_idx=self._step_idx)

    def stop_logging(self, *, generate_report: bool = True) -> None:
        if self._ingestion is None:
            return
        self._generate_report = generate_report
        # Overwrite the "Steps" row seeded in start_logging so the metadata
        # reflects what actually ran (start_logging seeded "0 / n_steps").
        # self._step_idx is the count of step_started signals received,
        # which is the true completed-step count and survives abort/error
        # (unlike the pane's _repeats_completed which resets on abort).
        stop_dt = datetime.now()
        meta = {"Steps": f"{self._step_idx} / {self._n_steps}"}
        if self._start_dt is not None:
            elapsed = stop_dt - self._start_dt
            meta["Start Time"] = self._start_dt.strftime(TIME_FMT)
            meta["Stop Time"] = stop_dt.strftime(TIME_FMT)
            meta["Elapsed Time"] = _format_elapsed(elapsed)
        self._ingestion.log_metadata(meta)
        _listener.clear_active_logger()
        self.flush_scheduler(self)

    def _drain_media_captures(self) -> None:
        """Pull every camera capture cached this run out of the shared
        app_globals bucket and into the ingestion. Mirrors legacy
        ``protocol_data_logger.generate_and_save_report`` which sweeps
        the same Redis key with ``force=True`` because captures land
        asynchronously and may arrive after stop_logging."""
        ing = self._ingestion
        if ing is None:
            return
        try:
            captures = list(app_globals.get(MEDIA_CAPTURES_KEY) or [])
        except Exception as e:                    # pragma: no cover - defensive
            logger.debug(f"could not read media_captures bucket: {e}")
            return
        for payload in captures:
            try:
                ing.log_media(MediaCaptureMessageModel.model_validate_json(payload))
            except Exception as e:                # pragma: no cover - defensive
                logger.warning(f"media drain entry failed: {e}")

    def _flush(self) -> None:
        ing = self._ingestion
        if ing is None:
            return
        # Drain camera captures BEFORE building the report so the Media
        # Captures section sees this run's videos/images.
        self._drain_media_captures()
        report_path = None
        report_error = None
        try:
            json_path, csv_path = LoggingPersistence.write_data_files(
                self._device_context.experiment_directory, self._start_time,
                ing.entries, ing.columns)
            if self._generate_report:
                html = LoggingReport.build_html(
                    entries=ing.entries, columns=ing.columns, metadata=ing.metadata,
                    media=ing.media, device_context=self._device_context,
                    notes=None, data_files=[json_path, csv_path])
                report_path = LoggingReport.write_report(
                    self._device_context.experiment_directory, html)
                self.all_report_paths.append(report_path)
                logger.info(f"Report written to {report_path}")

        except Exception as e:
            logger.error(f"protocol logging flush failed: {e}")
            report_path = None
            report_error = str(e)
        finally:
            self._ingestion = None
        # Notify the GUI (report saved / skipped). Outside the try so a
        # callback error is not misreported as a flush failure.
        if self.completion_callback is not None:
            try:
                self.completion_callback(report_path)
            except Exception as e:
                logger.error(f"logging completion callback failed: {e}")
        # If the user asked for a report and it failed, surface it instead of
        # leaving them with the same silent no-op as an intentional skip.
        if (report_error is not None and self._generate_report
                and self.report_failure_callback is not None):
            try:
                self.report_failure_callback(report_error)
            except Exception as e:
                logger.error(f"logging failure callback failed: {e}")

    # --- listener forwards (may run on a worker thread) ---
    def on_capacitance(self, message) -> None:
        ing = self._ingestion
        if ing is not None:
            ing.log_capacitance(message)

    def on_actuation(self, message) -> None:
        ing = self._ingestion
        if ing is None:
            return
        try:
            data = json.loads(message)
        except (ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        channels = data.get("channels", []) or []
        areas = getattr(self._device_context, "channel_areas", {}) or {}
        area = sum(float(areas.get(int(ch), 0.0)) for ch in channels)
        ing.set_actuation(actuated_channels=channels, actuated_area=area)

    def on_media(self, message) -> None:
        ing = self._ingestion
        if ing is None:
            return
        try:
            ing.log_media(MediaCaptureMessageModel.model_validate_json(message))
        except Exception as e:                 # pragma: no cover - defensive
            logger.warning(f"media log failed: {e}")

    def on_calibration(self, message) -> None:
        """CALIBRATION_DATA payload --> capacitance-per-unit-area. Lets the
        Force column populate on a live run (legacy parity); ignored
        until calibration data arrives, and invalid data leaves the
        previous value untouched."""
        ing = self._ingestion
        if ing is None:
            return
        try:
            data = json.loads(message)
        except (ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        cpa = _capacitance_per_unit_area(
            data.get(LIQUID_CAPACITANCE_KEY),
            data.get(FILLER_CAPACITANCE_KEY))
        if cpa is not None:
            ing.update_capacitance_per_unit_area(cpa)

    def update_capacitance_per_unit_area(self, value) -> None:
        ing = self._ingestion
        if ing is not None:
            ing.update_capacitance_per_unit_area(value)
