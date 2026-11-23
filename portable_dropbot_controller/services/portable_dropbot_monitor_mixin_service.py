# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import atexit
import json
import time

# Third-party imports.
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import (
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_STOPPED,
)
from apscheduler.triggers.interval import IntervalTrigger
from dropbot_portable import DropBotSession, port_lease
from serial.tools import list_ports

# Enthought library imports.
from traits.api import Bool, Instance, Str, provides

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..board_firmware import BoardFirmwareMixin
from ..consts import MONITOR_INTERVAL_S, PORTS_UPDATED, firmware_versions_publisher
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..port_lease_guard import PortLeaseGuard
from ..session_shutdown import deenergize_session

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotMonitorMixinService(BoardFirmwareMixin):
    id = Str("portable_dropbot_monitor_mixin_service")
    name = Str("Portable Dropbot Monitor Mixin")
    monitor_scheduler = Instance(
        BackgroundScheduler,
        desc="Scans serial ports while disconnected; polls status while connected.",
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
    #: Why the last connect attempt failed (exception type and
    #: message), reported instead of the generic handshake text;
    #: cleared by a successful connect.
    _last_connect_error = Str()
    #: The vendor port lease: our use claim while connected, and the yield
    #: to a firmware update that takes priority on our port.
    port_lease_guard = Instance(PortLeaseGuard, ())
    #: The port of the live connection, for the lease checks.
    _connected_port = Str()

    def on_start_device_monitoring_request(self, *args, **kwargs):
        if self.portable_dropbot_connection_active and self.proxy is not None:
            self._publish_connected()
            return

        if isinstance(self.monitor_scheduler, BackgroundScheduler):
            if self.monitor_scheduler.state == STATE_RUNNING:
                logger.info("Portable Dropbot monitoring already running.")
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
        # Interpreter-exit backstop: atexit callbacks run before Python
        # kills executor pools, so the scheduler dies quietly even on an
        # exit path that never reaches plugin stop (a signal handler's
        # sys.exit, a killed window).
        atexit.register(self._shutdown_monitor_scheduler)
        logger.info("Portable Dropbot monitor started.")

    def cleanup(self):
        """Stop the port scanner before the connection teardown: a
        BackgroundScheduler nothing shuts down outlives plugin stop,
        and once interpreter shutdown kills its executor pool every
        tick spams 'cannot schedule new futures after shutdown'."""
        self._shutdown_monitor_scheduler()
        self._deenergize("app exit")
        super().cleanup()
        self.port_lease_guard.release()

    def _shutdown_monitor_scheduler(self):
        """Idempotent scheduler shutdown, shared by cleanup and the
        atexit backstop."""
        scheduler = self.monitor_scheduler
        if (
            isinstance(scheduler, BackgroundScheduler)
            and scheduler.state != STATE_STOPPED
        ):
            try:
                scheduler.shutdown(wait=False)
                logger.info("Portable Dropbot monitor stopped.")
            except Exception as exc:
                logger.debug(f"Error stopping the Portable Dropbot monitor: {exc}")

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
        logger.info("Portable Dropbot disconnect requested; pausing the port scan.")
        self._user_disconnected = True
        if (
            isinstance(self.monitor_scheduler, BackgroundScheduler)
            and self.monitor_scheduler.state == STATE_RUNNING
        ):
            self.monitor_scheduler.pause()
        self.portable_dropbot_connection_active = False

        if self.proxy is not None:
            self._deenergize("user disconnect")

            try:
                self.proxy.disconnect()
            except Exception as exc:
                logger.debug(f"Error closing the session on user disconnect: {exc}")
            self.proxy = None

        self._forget_connection()
        self._publish_disconnected()

    def on_connect_to_port_request(self, message):
        """Explicit user-chosen serial port from the status pane's
        port picker. A named port earns the full autodetect baud
        ladder, exactly like the preference hint, and a failure is
        surfaced as an error signal instead of the scanner's silent
        debug line."""
        self._user_disconnected = False
        # The user's own connect takes over from a yield (vendor UI); a
        # port still reserved is refused by the lease claim itself.
        self.port_lease_guard.end_yield()
        port_name = str(message or "").strip()
        if not port_name:
            self.on_retry_connection_request(message)
            return
        if self.portable_dropbot_connection_active:
            logger.info(
                f"Connect to {port_name} ignored: Portable Dropbot already connected."
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

                # A user disconnect paused the scanner, and with it the
                # status poll: a successful connect must restart it.
                if (
                    self.monitor_scheduler is not None
                    and self.monitor_scheduler.state == STATE_PAUSED
                ):
                    self.monitor_scheduler.resume()
                    logger.info(
                        f"Resumed Portable Dropbot monitor after connect "
                        f"on {port_name}."
                    )
            else:
                reason = (
                    self._last_connect_error
                    or "no Portable Dropbot answered the login handshake"
                )
                logger.warning(f"Connect to {port_name} failed: {reason}")
                self._publish_error(f"connect to {port_name}", reason)
        finally:
            self._probing = False

    def on_retry_connection_request(self, message):
        self._user_disconnected = False
        self.port_lease_guard.end_yield()

        if self.portable_dropbot_connection_active:
            logger.info("Retry ignored: Portable Dropbot already connected.")
            return
        if (
            self.monitor_scheduler is not None
            and self.monitor_scheduler.state == STATE_PAUSED
        ):
            self.monitor_scheduler.resume()
            logger.info("Retry requested. Resumed Portable Dropbot monitor.")
            return
        self.on_start_device_monitoring_request(message)

    def _monitor_tick(self):
        """Every tick: while connected, publish a fresh status
        snapshot (which doubles as the liveness check — a serial
        failure inside it triggers the disconnect path); while
        disconnected, return port candidates to try. A firmware update
        taking priority on our port disconnects us, and scanning pauses
        until it lets go."""
        if self.portable_dropbot_connection_active and self.proxy is not None:
            holder = self.port_lease_guard.other_holder(self._connected_port)

            if holder is not None:
                self._yield_port_to_firmware_update(holder)
                return []

            # Motion runs outside the proxy lock, but a multi-call
            # sequence (the calibration macro) still holds it. Blocking
            # on it would stretch this tick past the interval —
            # apscheduler then skip-warns every fire until it ends — for
            # a snapshot that is stale the moment it is taken. Skip it;
            # the post-action republish refreshes everything anyway.
            if not self._proxy_lock.acquire(blocking=False):
                return []
            try:
                self._publish_status_snapshot()
            finally:
                self._proxy_lock.release()
            return []

        if self.port_lease_guard.scan_paused():
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

                # Never open a port a firmware update holds priority on.
                if self.port_lease_guard.other_holder(port_name) is not None:
                    logger.debug(f"Skipping {port_name}: reserved by a firmware update")
                    continue

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
            # Register as a port user before opening it, like the vendor
            # UI: refused while a firmware update holds priority, and a
            # flash that starts later waits for us to let go.
            self.port_lease_guard.claim(port_name)
            session = DropBotSession()
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

            firmware = self._read_board_firmware(session)
            # HV follows realtime mode, and every connection starts with
            # both off (the previous link's end reset realtime): only the
            # operator's realtime toggle after this point energizes the
            # board. Sent before the connection goes active, so no realtime
            # request can land in between.
            self._end_realtime_mode()
            session.sig.hv_enable(0, 0)
            self._connected_port = port_name
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
            self._publish_connected()
            firmware_versions_publisher.publish(firmware)
            self._publish_status_snapshot()
            logger.info(f"Connected to Portable Dropbot on {port_name}")
            self._error_shown = False
            self._last_connect_error = ""

            return True
        except Exception as exc:
            if session is not None:
                try:
                    session.disconnect()
                except Exception:
                    pass
            self.proxy = None
            self.portable_dropbot_connection_active = False
            self._forget_connection()
            self._last_connect_error = f"{type(exc).__name__}: {exc}"

            if not self._error_shown:
                logger.debug(f"Connection attempt failed on {port_name}: {exc}")
                self._error_shown = True
            return False

    # ------------------------------------------------------------------ #
    # Port lease and disconnect                                            #
    # ------------------------------------------------------------------ #
    def _yield_port_to_firmware_update(self, holder):
        """Another process (the vendor flash tool) took priority on our
        port: de-energize, disconnect and keep scanning paused until it
        lets go."""
        port = self._connected_port
        self.port_lease_guard.begin_yield(port, holder)
        self._publish_error(
            f"connection on {port}",
            f"the port is reserved by a firmware update "
            f"({port_lease.describe(holder)}); reconnecting once it finishes",
        )
        self._deenergize("firmware update yield")
        self.on_disconnected_signal("")

    def _deenergize(self, reason):
        """HV off, electrodes cleared and PMT off before a deliberate close
        of the port (see session_shutdown)."""

        if self.proxy is None:
            return

        steps = deenergize_session(self.proxy)
        logger.info(
            f"Portable Dropbot de-energized for {reason}: "
            f"{'; '.join(steps) or 'signal board not attached'}"
        )

    def _end_realtime_mode(self):
        """Realtime off, published: the frontend's own realtime-off request
        is refused while disconnected, and a realtime left on would let the
        next connection energize the board without the operator."""

        if self.realtime_mode:
            self.realtime_mode = False
            self._publish_realtime_mode()

    def _forget_connection(self):
        """Per-connection state ends with the link: realtime mode ends, the
        firmware versions become unknown, and the port use claim is dropped
        — only once the port is closed, as the vendor worker does."""
        self._end_realtime_mode()
        self.board_firmware_versions = {}
        self._connected_port = ""
        self.port_lease_guard.release()

    def on_connected_signal(self, message):
        self.portable_dropbot_connection_active = True

    def on_disconnected_signal(self, message):
        if self.proxy is not None:
            try:
                self.proxy.disconnect()
            except Exception:
                pass
            self.proxy = None

        self._forget_connection()
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
