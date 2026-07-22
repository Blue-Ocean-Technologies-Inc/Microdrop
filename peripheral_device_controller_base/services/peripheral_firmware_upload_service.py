"""Shared firmware-upload backend service for Pico-family peripherals.

Runs firmware_uploader.upload_firmware on a worker thread, streaming each
progress line onto ``<device>/signals/firmware_upload_log`` so any frontend
can render a live console. The accepted run is announced on
``firmware_upload_started`` and the outcome ({"success": bool}, or
{"error": str} on a crash) on ``firmware_upload_finished``.

Device-agnostic: every topic is derived from ``self._device_name`` (set by
the composed controller base), so a concrete device only needs a thin
subclass that ``@provides`` its own control-mixin interface and narrows the
``proxy`` type. Compose it exactly like the monitor / command-setter mixins.
"""

import json
import threading

from traits.api import Any, HasTraits, Instance

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    firmware_upload_finished_topic,
    firmware_upload_log_topic,
    firmware_upload_started_topic,
)
from ..firmware_uploader import upload_firmware
from ..firmware_upload_datamodels import UploadFirmwareData

from logger.logger_service import get_logger
logger = get_logger(__name__)


class PeripheralFirmwareUploadService(HasTraits):
    """Flashes a peripheral board's MicroPython firmware.

    Port resolution: an explicit requested port wins; otherwise a connected
    proxy's stored port is reused directly — the board is already
    identified, no whoami probing needed. Whenever the target port is the
    proxy's own, the proxy is released first via the composed controller's
    ``cleanup()`` (the uploader needs exclusive port access, and cleanup also
    stops the monitor so it can't reclaim the port mid-flash), and device
    monitoring is re-requested once the upload ends so the freshly flashed
    board reconnects.

    The upload thread and the timeout timer publish from non-worker threads —
    same precedent as the proxy's telemetry reader thread. Cancel and timeout
    both set the run's cancel event, which the uploader honours between steps.
    """

    #: Narrowed to the device's serial proxy by the concrete subclass.
    proxy = Any()

    #: The running upload thread (None / dead while idle).
    upload_thread = Instance(threading.Thread)
    #: Set to abort the running upload (cancel request or timeout).
    upload_cancel_event = Instance(threading.Event)
    #: Cancels the upload at the request's timeout (None when no timeout).
    upload_timeout_timer = Instance(threading.Timer)
    #: Serializes upload start/cancel against the upload thread's completion.
    upload_state_lock = Any()

    def _upload_state_lock_default(self):
        return threading.Lock()

    # ---- device-derived topics -------------------------------------------

    @property
    def _upload_started_topic(self):
        return firmware_upload_started_topic(self._device_name)

    @property
    def _upload_log_topic(self):
        return firmware_upload_log_topic(self._device_name)

    @property
    def _upload_finished_topic(self):
        return firmware_upload_finished_topic(self._device_name)

    @property
    def _start_device_monitoring_topic(self):
        return f"{self._device_name}/requests/start_device_monitoring"

    # ---- request handlers ------------------------------------------------

    def on_upload_firmware_request(self, body):
        """Validate an UploadFirmwareData payload and launch one upload;
        a request arriving while an upload runs is logged and ignored."""
        data = UploadFirmwareData(**json.loads(body))
        with self.upload_state_lock:
            if self.upload_thread is not None and self.upload_thread.is_alive():
                publish_message(
                    message="A firmware upload is already running — "
                            "request ignored.",
                    topic=self._upload_log_topic)
                return
            port, proxy_released = self._resolve_upload_port(data)
            self.upload_cancel_event = threading.Event()

            started_message = (
                f"Starting firmware upload from "
                f"{data.single_file or data.firmware_source} "
                f"(port: {port or 'auto-detect'}"
                f"{', dry run' if data.dry_run else ''})")
            publish_message(message=started_message,
                            topic=self._upload_started_topic)
            logger.info(started_message)

            if data.upload_timeout_s > 0:
                self.upload_timeout_timer = threading.Timer(
                    data.upload_timeout_s, self._cancel_timed_out_upload,
                    args=(self.upload_cancel_event, data.upload_timeout_s,
                          self._upload_log_topic))
                self.upload_timeout_timer.daemon = True
                self.upload_timeout_timer.start()
            self.upload_thread = threading.Thread(
                target=self._run_upload,
                args=(data, port, proxy_released, self.upload_cancel_event),
                daemon=True)
            self.upload_thread.start()

    def on_cancel_firmware_upload_request(self, body):
        """Abort the running upload; the uploader stops at the next step
        boundary and reports through the normal finish path."""
        with self.upload_state_lock:
            if self.upload_thread is None or not self.upload_thread.is_alive():
                return
            self._publish_upload_log_line(
                "Cancel requested — stopping the upload at the next step.")
            self.upload_cancel_event.set()

    # ---- upload run ------------------------------------------------------

    def _resolve_upload_port(self, data):
        """The port to flash and whether the proxy was released for it.

        Whenever the target port is the connected proxy's own (explicitly, or
        because the empty auto port resolves to it), the proxy must go: the
        uploader needs exclusive access to the port.
        """
        port = data.port
        if self.proxy is not None:
            if not port:
                port = self.proxy.port
            if port == self.proxy.port:
                self._publish_upload_log_line(
                    f"Disconnecting the board on {port} to free the port for "
                    f"the upload.")
                self.cleanup()
                return port, True
        return port, False

    def _run_upload(self, data, port, proxy_released, cancel_event):
        """Upload thread: run the uploader with a topic-publishing log, then
        report the outcome; if the proxy was released for this upload,
        re-request monitoring so the freshly flashed board reconnects."""
        try:
            success = upload_firmware(
                firmware_path=data.firmware_source,
                port=port or None,
                reset_device=data.reset_after_upload,
                single_file=data.single_file or None,
                no_format=data.skip_filesystem_format,
                update_config=data.update_config,
                device_id=data.device_id,
                dry_run=data.dry_run,
                hwids=getattr(self, "_default_hwids", None) or None,
                log=self._publish_upload_log_line,
                cancel_event=cancel_event,
            )
            finished_payload = {"success": success}
        except Exception as e:
            logger.exception("Firmware upload crashed")
            finished_payload = {"error": str(e)}
        with self.upload_state_lock:
            if self.upload_timeout_timer is not None:
                self.upload_timeout_timer.cancel()
                self.upload_timeout_timer = None
        publish_message(message=json.dumps(finished_payload),
                        topic=self._upload_finished_topic)
        if proxy_released:
            publish_message(message="",
                            topic=self._start_device_monitoring_topic)

    def _publish_upload_log_line(self, line):
        """Every uploader progress line goes to both the dialog's log console
        (topic) and the regular logger, so a headless run is traceable too."""
        publish_message(message=line, topic=self._upload_log_topic)
        logger.info(line)

    @staticmethod
    def _cancel_timed_out_upload(cancel_event, upload_timeout_s, log_topic):
        if cancel_event.is_set():
            return
        message = f"Upload timed out after {upload_timeout_s} s — aborting."
        publish_message(message=message, topic=log_topic)
        logger.info(message)
        cancel_event.set()
