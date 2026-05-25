"""GUI-thread controller that turns executor lifecycle signals into a
run's worth of logged artifacts. Owns a LoggingIngestion per run; the
logging listener forwards capacitance/actuation/media to it. Settling
flush is deferred so in-flight capacitance after 'done' is captured."""

import json
import time
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


class ProtocolLoggingController:
    def __init__(self, *, settling_provider: Optional[Callable[[], float]] = None,
                 flush_scheduler: Optional[Callable[["ProtocolLoggingController"], None]] = None):
        self._settling_provider = settling_provider or _default_settling_provider
        self._flush_scheduler = flush_scheduler or _qtimer_flush_scheduler
        self._ingestion: Optional[LoggingIngestion] = None
        self._device_context = None
        self._step_idx = 0
        self._start_time = ""

    # --- executor signal wiring ---
    def attach(self, qsignals) -> None:
        qsignals.step_started.connect(self._on_step_started)
        qsignals.protocol_finished.connect(lambda: self.stop_logging(self._step_idx))
        qsignals.protocol_aborted.connect(lambda: self.stop_logging(self._step_idx))
        qsignals.protocol_error.connect(lambda _msg: self.stop_logging(self._step_idx))

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

    def stop_logging(self, completed_steps) -> None:
        if self._ingestion is None:
            return
        self._ingestion.log_metadata({"Completed Steps": completed_steps})
        _listener.clear_active_logger()
        self._flush_scheduler(self)

    def _flush(self) -> None:
        ing = self._ingestion
        if ing is None:
            return
        try:
            LoggingPersistence.write_data_files(
                self._device_context.experiment_directory, self._start_time,
                ing.entries, ing.columns)
            html = LoggingReport.build_html(
                entries=ing.entries, columns=ing.columns, metadata=ing.metadata,
                media=ing.media, device_context=self._device_context, notes=None)
            LoggingReport.write_report(
                self._device_context.experiment_directory, html)
        except Exception as e:
            logger.error(f"protocol logging flush failed: {e}")
        finally:
            self._ingestion = None

    # --- listener forwards (may run on a worker thread) ---
    def on_capacitance(self, message) -> None:
        if self._ingestion is not None:
            self._ingestion.log_capacitance(message)

    def on_actuation(self, message) -> None:
        if self._ingestion is None:
            return
        try:
            channels = json.loads(message).get("channels", []) or []
        except (ValueError, TypeError):
            return
        areas = getattr(self._device_context, "channel_areas", {}) or {}
        area = sum(float(areas.get(int(ch), 0.0)) for ch in channels)
        self._ingestion.set_actuation(actuated_channels=channels, actuated_area=area)

    def on_media(self, message) -> None:
        if self._ingestion is None:
            return
        try:
            from device_viewer.models.media_capture_model import (
                MediaCaptureMessageModel,
            )
            self._ingestion.log_media(MediaCaptureMessageModel.model_validate_json(message))
        except Exception as e:                 # pragma: no cover - defensive
            logger.warning(f"media log failed: {e}")

    def update_capacitance_per_unit_area(self, value) -> None:
        if self._ingestion is not None:
            self._ingestion.update_capacitance_per_unit_area(value)
