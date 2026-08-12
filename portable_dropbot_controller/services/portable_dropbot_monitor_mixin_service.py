from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import (
    STATE_PAUSED, STATE_RUNNING, STATE_STOPPED,
)
from apscheduler.triggers.interval import IntervalTrigger
from serial.tools import list_ports
from traits.api import Bool, HasTraits, Instance, Str, provides

from logger.logger_service import get_logger

from ..consts import MONITOR_INTERVAL_S
from ..driver.session import DropletBotSession
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotMonitorMixinService(HasTraits):
    id = Str("portable_dropbot_monitor_mixin_service")
    name = Str("Portable Dropbot Monitor Mixin")
    monitor_scheduler = Instance(
        BackgroundScheduler,
        desc="Scans serial ports while disconnected; polls status "
             "while connected.",
    )
    _error_shown = Bool(False)
    #: A probe round is running: ticks fire every MONITOR_INTERVAL_S
    #: but a multi-port round can outlast one, and two rounds fighting
    #: over the same ports produce interleaved half-logins.
    _probing = Bool(False)
    portable_dropbot_connection_active = Bool(False)

    def on_start_device_monitoring_request(self, *args, **kwargs):
        if self.portable_dropbot_connection_active \
                and self.proxy is not None:
            self._publish_connected()
            return

        if isinstance(self.monitor_scheduler, BackgroundScheduler):
            if self.monitor_scheduler.state == STATE_RUNNING:
                logger.info("Portable Dropbot monitoring already "
                            "running.")
                return
            if self.monitor_scheduler.state == STATE_STOPPED:
                self.monitor_scheduler.start()
                logger.info("Portable Dropbot monitoring restarted.")
                return
            if self.monitor_scheduler.state == STATE_PAUSED:
                self.monitor_scheduler.resume()
                logger.info("Portable Dropbot monitoring resumed.")
                return

        scheduler = BackgroundScheduler()
        scheduler.add_job(func=self._monitor_tick,
                          trigger=IntervalTrigger(
                              seconds=MONITOR_INTERVAL_S))
        scheduler.add_listener(self._on_ports_discovered,
                               EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler
        self.monitor_scheduler.start()
        logger.info("Portable Dropbot monitor started.")

    def on_retry_connection_request(self, message):
        if self.portable_dropbot_connection_active:
            logger.info("Retry ignored: Portable Dropbot already "
                        "connected.")
            return
        if self.monitor_scheduler is not None \
                and self.monitor_scheduler.state == STATE_PAUSED:
            self.monitor_scheduler.resume()
            logger.info("Retry requested. Resumed Portable Dropbot "
                        "monitor.")
            return
        self.on_start_device_monitoring_request(message)

    def _monitor_tick(self):
        """Every tick: while connected, publish a fresh status
        snapshot (which doubles as the liveness check — a serial
        failure inside it triggers the disconnect path); while
        disconnected, return port candidates to try."""
        if self.portable_dropbot_connection_active \
                and self.proxy is not None:
            self._publish_status_snapshot()
            return []
        return self._candidate_ports()

    def _candidate_ports(self):
        """The preference hint first, then USB-style ports (the usual
        transport), then the rest — the hardware has no VID:PID
        identity, so the login handshake is the filter. Onboard UARTs
        (a Pi's /dev/ttyAMA*) land last: they always exist and never
        answer."""
        present = [port.device for port in list_ports.comports()]
        usb_like = [port for port in present
                    if "USB" in port.upper() or "ACM" in port.upper()
                    or port.upper().startswith("COM")]
        others = [port for port in present if port not in usb_like]
        ports = usb_like + others
        hint = str(self.preferences.port_hint or "").strip()
        if hint:
            ports = [hint] + [port for port in ports if port != hint]
        return ports

    def _on_ports_discovered(self, event):
        if self.portable_dropbot_connection_active or self._probing:
            return
        self._probing = True
        try:
            hint = str(self.preferences.port_hint or "").strip()
            for port_name in (event.retval or []):
                if self.portable_dropbot_connection_active:
                    return
                # The full 4-rate autodetect ladder costs seconds and
                # a dozen warning lines per silent port; while
                # scanning, one login at the configured baud is the
                # filter. Only the hinted port earns the ladder (a
                # board provisioned to a non-default rate is a board
                # the user knows the port of).
                if self._attempt_connect(port_name,
                                         autodetect=port_name == hint):
                    return
        finally:
            self._probing = False

    def _attempt_connect(self, port_name: str,
                         autodetect: bool = False) -> bool:
        session = None
        try:
            session = DropletBotSession()
            if not session.connect(port=port_name,
                                   baudrate=int(self.preferences.baud_rate),
                                   autodetect=autodetect):
                raise ConnectionError("login handshake failed")
            if not session.connected:
                # The driver's single-rate connect returns True as
                # soon as the port OPENS (legacy behavior) — an
                # onboard UART "connects" that way while both login
                # commands time out. Only an answered login counts.
                raise ConnectionError(
                    "port opened but neither board answered login")
            self.proxy = session
            self.portable_dropbot_connection_active = True
            # Alarms stream in unsolicited; hand them straight to the
            # status pane as the driver's decoded strings.
            session.uart.on_alarm = self._publish_alarm
            self.voltage = int(self.preferences.default_voltage)
            self.frequency = int(self.preferences.default_frequency)
            self.light_intensity = int(
                self.preferences.default_light_intensity)
            self._apply_actuation()
            self._apply_light_intensity()
            self._publish_connected()
            self._publish_status_snapshot()
            logger.info(f"Connected to Portable Dropbot on {port_name}")
            self._error_shown = False
            return True
        except Exception as exc:
            if session is not None:
                try:
                    session.disconnect()
                except Exception:
                    pass
            self.proxy = None
            self.portable_dropbot_connection_active = False
            if not self._error_shown:
                logger.debug(f"Connection attempt failed on "
                             f"{port_name}: {exc}")
                self._error_shown = True
            return False

    def on_connected_signal(self, message):
        self.portable_dropbot_connection_active = True

    def on_disconnected_signal(self, message):
        if self.proxy is not None:
            try:
                self.proxy.disconnect()
            except Exception:
                pass
            self.proxy = None
        logger.warning("Portable Dropbot disconnected.")
        if self.portable_dropbot_connection_active:
            self._publish_disconnected()
        self.portable_dropbot_connection_active = False
        if self.monitor_scheduler is not None:
            if self.monitor_scheduler.state == STATE_PAUSED:
                self.monitor_scheduler.resume()
            elif self.monitor_scheduler.state == STATE_STOPPED:
                self.monitor_scheduler.start()
