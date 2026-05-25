"""GUI-thread controller that turns executor lifecycle signals into a
run's worth of logged artifacts. Owns a LoggingIngestion per run; the
logging listener forwards capacitance/actuation/media to it. Settling
flush is deferred so in-flight capacitance after 'done' is captured."""

import json
import time
from pathlib import Path
from typing import Callable, Optional

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
        self._start_time = ""
        self._generate_report = True

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
        self._start_time = time.strftime("%Y%m%d_%H%M%S")
        self._ingestion.log_metadata({
            "Experiment Directory": str(device_context.experiment_directory),
            "Device SVG": str(getattr(device_context, "device_svg_path", "")),
            "Steps": f"0 / {n_steps}",
        })
        _listener.set_active_logger(self)

    def _on_step_started(self, row) -> None:
        if self._ingestion is None:
            return
        self._step_idx += 1
        self._ingestion.set_step(step_id=getattr(row, "uuid", ""),
                                 step_idx=self._step_idx)

    def stop_logging(self, completed_steps, *, generate_report: bool = True) -> None:
        if self._ingestion is None:
            return
        self._generate_report = generate_report
        self._ingestion.log_metadata({"Completed Steps": completed_steps})
        _listener.clear_active_logger()
        self._flush_scheduler(self)

    def _flush(self) -> None:
        ing = self._ingestion
        if ing is None:
            return
        report_path = None
        try:
            LoggingPersistence.write_data_files(
                self._device_context.experiment_directory, self._start_time,
                ing.entries, ing.columns)
            if self._generate_report:
                html = LoggingReport.build_html(
                    entries=ing.entries, columns=ing.columns, metadata=ing.metadata,
                    media=ing.media, device_context=self._device_context, notes=None)
                report_path = LoggingReport.write_report(
                    self._device_context.experiment_directory, html)
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
        """CALIBRATION_DATA payload → capacitance-per-unit-area. Lets the
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
            data.get("liquid_capacitance_over_area"),
            data.get("filler_capacitance_over_area"))
        if cpa is not None:
            ing.update_capacitance_per_unit_area(cpa)

    def update_capacitance_per_unit_area(self, value) -> None:
        ing = self._ingestion
        if ing is not None:
            ing.update_capacitance_per_unit_area(value)
