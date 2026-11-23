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
from dropbot_portable import DropBotSession
from dropbot_portable.port_utils import filter_serial_ports
from serial.tools import list_ports

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance, List, Set, Str, provides

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..connect_attempt import (
    ConnectAttempt,
    ConnectAttemptCancelled,
    ConnectAttemptTimeout,
)
from ..consts import (
    CONNECT_AUTODETECT_TIMEOUT_S,
    CONNECT_TIMEOUT_S,
    MONITOR_INTERVAL_S,
    PORTS_UPDATED,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotMonitorMixinService(HasTraits):
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
    #: Driver connects in flight (a scan round's and a user-chosen port's
    #: can overlap); cleanup abandons them so shutdown never waits on a
    #: port that swallowed the login write.
    _connect_attempts = List(Instance(ConnectAttempt))
    #: Plugin stop began: scan rounds end and no new connect is waited on.
    _monitor_stopping = Bool(False)
    #: Ports whose connect already timed out: the scan retries them every
    #: tick, the warning is logged once.
    _stalled_ports = Set(Str)

    def on_start_device_monitoring_request(self, *args, **kwargs):
        self._monitor_stopping = False

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
        # Interpreter-exit backstop for an exit path that never reaches
        # plugin stop (a signal handler's sys.exit, a killed window).
        # atexit runs only after concurrent.futures' own exit hook has
        # joined the executor's pool thread (daemon or not), so it cannot
        # rescue a stuck job: the connect deadline is what bounds that join.
        atexit.register(self._shutdown_monitor_scheduler)
        logger.info("Portable Dropbot monitor started.")

    def cleanup(self):
        """Abandon in-flight connects and stop the port scanner before the
        connection teardown. A BackgroundScheduler nothing shuts down
        outlives plugin stop, and once interpreter shutdown kills its
        executor pool every tick spams 'cannot schedule new futures after
        shutdown'; a connect stuck in the pool thread would keep the
        process alive (#1065)."""
        self._monitor_stopping = True
        self._abandon_connect_attempts()
        self._shutdown_monitor_scheduler()
        super().cleanup()

    def _abandon_connect_attempts(self):
        """Release every waiter on a driver connect; each attempt closes its
        own half-open port in the background."""
        attempts = list(self._connect_attempts)

        if attempts:
            logger.info(
                f"Abandoning Portable Dropbot connect on "
                f"{', '.join(attempt.port_name for attempt in attempts)}."
            )

        for attempt in attempts:
            attempt.abandon(ConnectAttemptCancelled("the monitor is stopping"))

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
            try:
                self.proxy.disconnect()
            except Exception as exc:
                logger.debug(f"Error closing the session on user disconnect: {exc}")
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
        """The preference hint first, then the driver's own port choice:
        endpoints that can never be the board are dropped (Bluetooth SPP
        ports, whose login write with no peer never completes — #1065 —
        and a Mac's debug console), USB-style ports sort before the rest
        (onboard UARTs such as a Pi's /dev/ttyAMA*). The hardware has no
        VID:PID identity, so the login handshake is the final filter."""
        ports = filter_serial_ports(list_ports.comports())
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
                if self.portable_dropbot_connection_active or self._monitor_stopping:
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
            session = DropBotSession()
            attempt = ConnectAttempt(
                session=session,
                port_name=port_name,
                connect_kwargs=dict(
                    port=port_name,
                    baudrate=int(self.preferences.baud_rate),
                    autodetect=autodetect,
                ),
            )
            self._connect_attempts.append(attempt)

            # cleanup sets the flag before abandoning the registered
            # attempts, so an attempt registered meanwhile is caught here.
            if self._monitor_stopping:
                attempt.abandon(ConnectAttemptCancelled("the monitor is stopping"))

            try:
                connected = attempt.run(
                    CONNECT_AUTODETECT_TIMEOUT_S if autodetect else CONNECT_TIMEOUT_S
                )
            finally:
                self._connect_attempts.remove(attempt)

            if attempt.abandoned:
                # The attempt's release thread closes this session.
                session = None
                raise attempt.error

            if attempt.error is not None:
                raise attempt.error

            if not connected:
                raise ConnectionError("login handshake failed")

            if self._monitor_stopping:
                raise ConnectAttemptCancelled("the monitor is stopping")

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
            session.sig.hv_enable(1 if self.realtime_mode else 0, 0)
            self._publish_connected()
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
            self._last_connect_error = f"{type(exc).__name__}: {exc}"

            if (
                isinstance(exc, ConnectAttemptTimeout)
                and port_name not in self._stalled_ports
            ):
                self._stalled_ports.add(port_name)
                logger.warning(
                    f"Portable Dropbot connect on {port_name} abandoned ({exc}); "
                    f"the port is probably not the board."
                )
            elif not self._error_shown:
                logger.debug(f"Connection attempt failed on {port_name}: {exc}")
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
