import json
import time

from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import (
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_STOPPED,
)
from apscheduler.triggers.interval import IntervalTrigger
from serial.tools import list_ports
from traits.api import Bool, HasTraits, Instance, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import MONITOR_INTERVAL_S, PORTS_UPDATED
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
        desc="Scans serial ports while disconnected; polls status " "while connected.",
    )
    _error_shown = Bool(False)
    #: A probe round is running: ticks fire every MONITOR_INTERVAL_S
    #: but a multi-port round can outlast one, and two rounds fighting
    #: over the same ports produce interleaved half-logins.
    _probing = Bool(False)
    portable_dropbot_connection_active = Bool(False)
    #: The user asked to disconnect: keep the scanner paused instead
    #: of re-acquiring the board on the next tick; any connect/retry
    #: request clears it.
    _user_disconnected = Bool(False)

    def on_start_device_monitoring_request(self, *args, **kwargs):
        if self.portable_dropbot_connection_active and self.proxy is not None:
            self._publish_connected()
            return

        if isinstance(self.monitor_scheduler, BackgroundScheduler):
            if self.monitor_scheduler.state == STATE_RUNNING:
                logger.info("Portable Dropbot monitoring already " "running.")
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
        scheduler.add_job(
            func=self._monitor_tick, trigger=IntervalTrigger(seconds=MONITOR_INTERVAL_S)
        )
        scheduler.add_listener(self._on_ports_discovered, EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler
        self.monitor_scheduler.start()
        logger.info("Portable Dropbot monitor started.")

    def on_refresh_ports_request(self, *args, **kwargs):
        """The frontend can run on a different machine than the
        hardware, so the backend owns port enumeration: answer with
        the scanner's own candidate ordering (preference hint first,
        USB-style ports next)."""
        ports = self._candidate_ports()
        logger.debug(f"Port refresh requested; candidates: {ports}")
        publish_message(topic=PORTS_UPDATED, message=json.dumps(ports))

    def on_disconnect_request(self, message):
        """User-requested disconnect: drop the link and leave the
        scanner paused, so the board stays disconnected until the
        user connects again."""
        if not self.portable_dropbot_connection_active:
            return
        logger.info("Portable Dropbot disconnect requested; pausing " "the port scan.")
        self._user_disconnected = True
        if (
            isinstance(self.monitor_scheduler, BackgroundScheduler)
            and self.monitor_scheduler.state == STATE_RUNNING
        ):
            self.monitor_scheduler.pause()
        self.portable_dropbot_connection_active = False
        if self.proxy is not None:
            try:
                self.proxy.disconnect()
            except Exception as exc:
                logger.debug(f"Error closing the session on user " f"disconnect: {exc}")
            self.proxy = None
        self._publish_disconnected()

    def on_connect_to_port_request(self, message):
        """Explicit user-chosen serial port from the status pane's
        port picker. A named port earns the full autodetect baud
        ladder, exactly like the preference hint, and a failure is
        surfaced as an error signal instead of the scanner's silent
        debug line."""
        self._user_disconnected = False
        port_name = str(message or "").strip()
        if not port_name:
            self.on_retry_connection_request(message)
            return
        if self.portable_dropbot_connection_active:
            logger.info(
                f"Connect to {port_name} ignored: Portable "
                f"Dropbot already connected."
            )
            self._publish_connected()
            return
        # Claim the probe guard so the next scheduled scan round does
        # not fight this attempt over the same port.
        self._probing = True
        try:
            if self._attempt_connect(port_name, autodetect=True):
                # A port the user pointed at is the best possible
                # hint for the next scan.
                self.preferences.port_hint = port_name
            else:
                self._publish_error(
                    f"connect to {port_name}",
                    "no Portable Dropbot answered the login handshake",
                )
        finally:
            self._probing = False

    def on_retry_connection_request(self, message):
        self._user_disconnected = False
        if self.portable_dropbot_connection_active:
            logger.info("Retry ignored: Portable Dropbot already " "connected.")
            return
        if (
            self.monitor_scheduler is not None
            and self.monitor_scheduler.state == STATE_PAUSED
        ):
            self.monitor_scheduler.resume()
            logger.info("Retry requested. Resumed Portable Dropbot " "monitor.")
            return
        self.on_start_device_monitoring_request(message)

    def _monitor_tick(self):
        """Every tick: while connected, publish a fresh status
        snapshot (which doubles as the liveness check — a serial
        failure inside it triggers the disconnect path); while
        disconnected, return port candidates to try."""
        if self.portable_dropbot_connection_active and self.proxy is not None:
            # A long driver call (home-all, a tray move) holds the
            # proxy lock for tens of seconds. Blocking on it would
            # stretch this tick past the interval — apscheduler then
            # skip-warns every fire until the move ends — for a
            # snapshot that is stale the moment it is taken. Skip it;
            # the post-action republish refreshes everything anyway.
            if not self._proxy_lock.acquire(blocking=False):
                return []
            try:
                self._publish_status_snapshot()
            finally:
                self._proxy_lock.release()
            return []
        return self._candidate_ports()

    def _candidate_ports(self):
        """The preference hint first, then USB-style ports (the usual
        transport), then the rest — the hardware has no VID:PID
        identity, so the login handshake is the filter. Onboard UARTs
        (a Pi's /dev/ttyAMA*) land last: they always exist and never
        answer."""
        present = [port.device for port in list_ports.comports()]
        usb_like = [
            port
            for port in present
            if "USB" in port.upper()
            or "ACM" in port.upper()
            or port.upper().startswith("COM")
        ]
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
            for port_name in event.retval or []:
                if self.portable_dropbot_connection_active:
                    return
                # The full 4-rate autodetect ladder costs seconds and
                # a dozen warning lines per silent port; while
                # scanning, one login at the configured baud is the
                # filter. Only the hinted port earns the ladder (a
                # board provisioned to a non-default rate is a board
                # the user knows the port of).
                if self._attempt_connect(port_name, autodetect=port_name == hint):
                    return
        finally:
            self._probing = False

    def _attempt_connect(self, port_name: str, autodetect: bool = False) -> bool:
        session = None
        try:
            session = DropletBotSession()
            if not session.connect(
                port=port_name,
                baudrate=int(self.preferences.baud_rate),
                autodetect=autodetect,
            ):
                raise ConnectionError("login handshake failed")
            if not session.connected:
                # The driver's single-rate connect returns True as
                # soon as the port OPENS (legacy behavior) — an
                # onboard UART "connects" that way while both login
                # commands time out. Only an answered login counts.
                raise ConnectionError("port opened but neither board answered login")
            if not session.uart.motor_board_connected:
                # connect() gives the motor board a single login try,
                # easy to lose right after the baud ladder — and an
                # unlogged motor board makes every motor call return a
                # silent False. Retry before giving up on it.
                for _ in range(2):
                    time.sleep(0.3)
                    if session.uart.BoardLogin("motor"):
                        break
            logger.info(
                f"Portable Dropbot boards on {port_name}: signal="
                f"{'yes' if session.uart.sig_board_connected else 'no'}"
                f", motor="
                f"{'yes' if session.uart.motor_board_connected else 'no'}"
            )
            if not session.uart.motor_board_connected:
                self._publish_error(
                    "motor board login",
                    "the motor board did not answer; motor controls "
                    "stay dead until a reconnect reaches it",
                )
            self.proxy = session
            self.portable_dropbot_connection_active = True
            # Alarms stream in unsolicited; hand them straight to the
            # status pane as the driver's decoded strings.
            session.uart.on_alarm = self._publish_alarm
            self.voltage = int(self.preferences.default_voltage)
            self.frequency = int(self.preferences.default_frequency)
            self.light_intensity = int(self.preferences.default_light_intensity)
            self._apply_actuation()
            self._apply_light_intensity()
            # Align the HV master enable with realtime mode (HV
            # follows the Realtime toggle): a freshly connected board
            # must not sit energized while realtime is off.
            session.uart.hv_enable(1 if self.realtime_mode else 0, 0)
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
                logger.debug(f"Connection attempt failed on " f"{port_name}: {exc}")
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
        if self._user_disconnected:
            # Deliberate disconnect: the scanner stays paused until
            # the user connects/retries again.
            return
        if self.monitor_scheduler is not None:
            if self.monitor_scheduler.state == STATE_PAUSED:
                self.monitor_scheduler.resume()
            elif self.monitor_scheduler.state == STATE_STOPPED:
                self.monitor_scheduler.start()
