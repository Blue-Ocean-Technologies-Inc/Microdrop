"""GUI-thread controller that turns executor lifecycle signals into a
run's worth of logged artifacts. Owns a LoggingIngestion per run; the
logging listener forwards capacitance/actuation/media to it. Settling
flush is deferred so in-flight capacitance after 'done' is captured."""

import datetime as _dt
import json
import time
from pathlib import Path
from typing import Callable, Optional

from device_viewer.consts import LIQUID_CAPACITANCE_KEY, FILLER_CAPACITANCE_KEY

_TIME_FMT = "%Y-%m-%d %H:%M:%S"

from logger.logger_service import get_logger

from pluggable_protocol_tree.services.logging import listener as _listener
from pluggable_protocol_tree.services.logging.ingestion import LoggingIngestion
from pluggable_protocol_tree.services.logging.persistence import LoggingPersistence
from pluggable_protocol_tree.services.logging.reporting import LoggingReport

logger = get_logger(__name__)


def _default_settling_provider() -> float:
    try:
        from protocol_grid.preferences import ProtocolPreferences
        return float(ProtocolPreferences().logs_settling_time_s)
    except Exception as e:                     # pragma: no cover - defensive
        logger.debug(f"settling pref unavailable, default 3.0s: {e}")
        return 3.0


def _qtimer_flush_scheduler(controller) -> None:
    from pyface.qt.QtCore import QTimer
    QTimer.singleShot(int(controller._settling_provider() * 1000),
                      controller._flush)


def _format_elapsed(delta: _dt.timedelta) -> str:
    """`H:MM:SS` for the metadata table (sub-second jitter is noise here)."""
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


_MEDIA_CAPTURES_KEY = "media_captures"


def _get_app_globals():
    """Open a handle to the shared Redis-backed app globals dict, or None
    when Redis is unreachable (tests, demos, headless). Caller treats None
    as "no media to drain"."""
    try:
        from microdrop_application.helpers import (
            get_microdrop_redis_globals_manager,
        )
        return get_microdrop_redis_globals_manager()
    except Exception as e:                     # pragma: no cover - defensive
        logger.debug(f"app_globals unavailable, media drain skipped: {e}")
        return None


def _capacitance_per_unit_area(liquid, filler) -> Optional[float]:
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


class ProtocolLoggingController:
    def __init__(self, *, settling_provider: Optional[Callable[[], float]] = None,
                 flush_scheduler: Optional[Callable[["ProtocolLoggingController"], None]] = None,
                 completion_callback: Optional[Callable[[Optional[Path]], None]] = None):
        self._settling_provider = settling_provider or _default_settling_provider
        self._flush_scheduler = flush_scheduler or _qtimer_flush_scheduler
        self._completion_callback = completion_callback
        self._ingestion: Optional[LoggingIngestion] = None
        self._device_context = None
        self._step_idx = 0
        self._n_steps = 0
        self._start_time = ""
        self._start_dt: Optional[_dt.datetime] = None
        self._generate_report = True
        self.all_report_paths: list[Path] = []

    # --- executor signal wiring ---
    def attach(self, qsignals) -> None:
        # Only the per-step context comes from the executor signals.
        # start_logging / stop_logging are driven by the pane: a
        # whole-protocol repeat run restarts the executor per repetition
        # (firing protocol_finished each time), so the pane stops logging
        # once at its single terminal point — keeping all repeats in one
        # log instead of stopping after the first.
        qsignals.step_started.connect(self._on_step_started)

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
        self._start_time = time.strftime("%Y%m%d_%H%M%S")
        self._start_dt = _dt.datetime.now()
        self._ingestion.log_metadata({
            "Experiment Directory": str(device_context.experiment_directory),
            "Device SVG": str(getattr(device_context, "device_svg_path", "")),
            "Steps": f"0 / {self._n_steps}",
        })
        # Reset the shared media-captures bucket so only THIS run's camera
        # output ends up in this run's report — _flush drains it back.
        # Camera capture path: device_viewer.views.camera_control_view.utils.
        # _cache_media_capture is a dramatiq actor that appends serialised
        # MediaCaptureMessageModel JSON to app_globals["media_captures"]
        # but never publishes the DEVICE_VIEWER_MEDIA_CAPTURED topic; the
        # listener wired in start_logging therefore can't see captures
        # live (legacy parity bug). Reading the bucket at flush time
        # closes the gap.
        ag = _get_app_globals()
        if ag is not None:
            try:
                ag[_MEDIA_CAPTURES_KEY] = []
            except Exception as e:                # pragma: no cover - defensive
                logger.debug(f"could not reset media_captures bucket: {e}")
        _listener.set_active_logger(self)

    def _on_step_started(self, row) -> None:
        if self._ingestion is None:
            return
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
        stop_dt = _dt.datetime.now()
        meta = {"Steps": f"{self._step_idx} / {self._n_steps}"}
        if self._start_dt is not None:
            elapsed = stop_dt - self._start_dt
            meta["Start Time"] = self._start_dt.strftime(_TIME_FMT)
            meta["Stop Time"] = stop_dt.strftime(_TIME_FMT)
            meta["Elapsed Time"] = _format_elapsed(elapsed)
        self._ingestion.log_metadata(meta)
        _listener.clear_active_logger()
        self._flush_scheduler(self)

    def _drain_media_captures(self) -> None:
        """Pull every camera capture cached this run out of the shared
        app_globals bucket and into the ingestion. Mirrors legacy
        ``protocol_data_logger.generate_and_save_report`` which sweeps
        the same Redis key with ``force=True`` because captures land
        asynchronously and may arrive after stop_logging."""
        ing = self._ingestion
        if ing is None:
            return
        ag = _get_app_globals()
        if ag is None:
            return
        try:
            captures = list(ag.get(_MEDIA_CAPTURES_KEY) or [])
        except Exception as e:                    # pragma: no cover - defensive
            logger.debug(f"could not read media_captures bucket: {e}")
            return
        if not captures:
            return
        try:
            from device_viewer.models.media_capture_model import (
                MediaCaptureMessageModel,
            )
        except Exception as e:                    # pragma: no cover - defensive
            logger.warning(f"media model unavailable, skipping drain: {e}")
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
        finally:
            self._ingestion = None
        # Notify the GUI (report saved / skipped). Outside the try so a
        # callback error is not misreported as a flush failure.
        if self._completion_callback is not None:
            try:
                self._completion_callback(report_path)
            except Exception as e:
                logger.error(f"logging completion callback failed: {e}")

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
            from device_viewer.models.media_capture_model import (
                MediaCaptureMessageModel,
            )
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
