from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
from apscheduler.triggers.interval import IntervalTrigger
from traits.api import Bool, HasTraits, Instance, Str, provides

from logger.logger_service import get_logger

from ..interfaces.i_opendrop_control_mixin_service import IOpenDropControlMixinService
from ..opendrop_serial_proxy import OpenDropSerialProxy
from ..port_discovery import find_opendrop_port

logger = get_logger(__name__)


@provides(IOpenDropControlMixinService)
class OpenDropMonitorMixinService(HasTraits):
    id = Str("opendrop_monitor_mixin_service")
    name = Str("OpenDrop Monitor Mixin")
    monitor_scheduler = Instance(
        BackgroundScheduler,
        desc="APScheduler job that periodically scans serial ports for OpenDrop.",
    )
    _error_shown = Bool(False)
    opendrop_connection_active = Bool(False)

    def on_start_device_monitoring_request(self, preferred_port):
        if self.opendrop_connection_active and self.proxy is not None:
            self._publish_connected()
            return

        if hasattr(self, "monitor_scheduler") and isinstance(self.monitor_scheduler, BackgroundScheduler):
            if self.monitor_scheduler.state == STATE_RUNNING:
                logger.info("OpenDrop monitoring already running.")
                return
            if self.monitor_scheduler.state == STATE_STOPPED:
                self.monitor_scheduler.start()
                logger.info("OpenDrop monitoring restarted.")
                return
            if self.monitor_scheduler.state == STATE_PAUSED:
                self.monitor_scheduler.resume()
                logger.info("OpenDrop monitoring resumed.")
                return

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=self._monitor_connection,
            trigger=IntervalTrigger(seconds=2),
        )
        scheduler.add_listener(self._on_port_discovered, EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler
        self.monitor_scheduler.start()
        logger.info("OpenDrop monitor started.")

    def on_retry_connection_request(self, message):
        if self.opendrop_connection_active:
            logger.info("Retry ignored: OpenDrop already connected.")
            return
        if self.monitor_scheduler is not None and self.monitor_scheduler.state == STATE_PAUSED:
            self.monitor_scheduler.resume()
            logger.info("Retry requested. Resumed OpenDrop monitor.")
            return
        self.on_start_device_monitoring_request(message)

    def _monitor_connection(self):
        """
        Run every 2s: if connected, verify serial is still valid; if not, try to discover and connect.
        Returns list of port candidates for _on_port_discovered (empty when connected and ok).
        """
        if self.opendrop_connection_active and self.proxy is not None:
            if not self.proxy.check_connection():
                logger.warning("OpenDrop connection check failed (device gone).")
                self.on_disconnected_signal("")
            return []
        return self._discover_port()

    def _discover_port(self):
        # Use explicit port hint if set, else find by OpenDrop VID:PID (e.g. Feather M0).
        port_hint = str(self.preferences.port_hint or "").strip()
        port = find_opendrop_port(port_hint=port_hint if port_hint else None)
        if port:
            return [port]
        return []

    def _on_port_discovered(self, event):
        if self.opendrop_connection_active:
            return

        candidates = event.retval or []
        for port_name in candidates:
            if self._attempt_connect(port_name):
                return

    def _attempt_connect(self, port_name: str) -> bool:
        proxy = None
        try:
            proxy = OpenDropSerialProxy(
                port=port_name,
                baud_rate=int(self.preferences.baud_rate),
                serial_timeout_s=float(self.preferences.serial_timeout_s),
            )
            proxy.connect()
            self.proxy = proxy
            self.opendrop_connection_active = True
            self._push_state_to_device(force=True)
            self._publish_connected()
            logger.info(f"Connected to OpenDrop on {port_name}")
            self._error_shown = False
            return True
        except Exception as exc:
            if proxy is not None:
                proxy.close()
            self.proxy = None
            self.opendrop_connection_active = False
            if not self._error_shown:
                logger.debug(f"Connection attempt failed on {port_name}: {exc}")
                self._error_shown = True
            return False

    def on_connected_signal(self, message):
        self.opendrop_connection_active = True

    def on_disconnected_signal(self, message):
        if self.proxy is not None:
            self.proxy.close()
            self.proxy = None
        logger.warning("OpenDrop disconnected.")
        if self.opendrop_connection_active:
            self._publish_disconnected()
        self.opendrop_connection_active = False
        if self.monitor_scheduler is not None:
            if self.monitor_scheduler.state == STATE_PAUSED:
                self.monitor_scheduler.resume()
            elif self.monitor_scheduler.state == STATE_STOPPED:
                self.monitor_scheduler.start()

