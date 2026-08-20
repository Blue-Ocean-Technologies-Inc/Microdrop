"""High-level DropletBot session API.

Wraps the low-level PortableDropbotService (DropletBotUart) with a
clean, Pythonic interface. Supports context manager usage::

    with DropletBotSession("/dev/ttyUSB0") as bot:
        bot.set_actuation(voltage_v=100, frequency_hz=10000)
        bot.actuate_channels([0, 1, 5, 10])
        caps = bot.measure_capacitance()
        print(caps)
"""

import json
import logging
import struct
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from .portable_dropbot_service import DropletBotUart, APP_BAUD_WHITELIST
from .commands import SignalBoard, MotorBoard

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapCalibration:
    """Host-side correction for the active-electrode capacitance measurement.

    The firmware (``cap_cali_measure_realtime``) returns a raw value
    ``C = amplitude_v / V_hv * C_cal`` with **no baseline subtraction**, and
    ``C_cal`` sits at its hardcoded nominal because the on-board calibration
    against the 10/100/470 pF references is not applied. Empirically a raw
    reading is therefore ``raw = offset_pf + true_pF / gain``:

    - ``offset_pf``: fixed stray (feedback path + HV-bus parasitic, ~12 pF),
      present on every reading once any electrode is active.
    - ``gain``: corrects the ``C_cal`` scale error (~1.30 against a 10 pF/
      electrode reference board, i.e. the raw reads ~23 % low).

    Corrected capacitance = ``(raw - offset_pf) * gain``. Defaults are a no-op.
    """

    gain: float = 1.0
    offset_pf: float = 0.0

# Electrode reference capacitor groups (from droplet_move.c check_pf_bits)
_CAP_470PF_CHANNELS = frozenset({49, 34, 26, 9, 70, 85, 93, 110})
_CAP_100PF_CHANNELS = frozenset({50, 52, 36, 37, 20, 21, 10, 4, 67, 69, 82, 83, 98, 99, 115, 109})
# 10pF = all remaining channels (0-119 minus 470 and 100 groups)


class DropletBotError(Exception):
    """Base exception for DropletBot operations."""


class DropletBotSession:
    """High-level API for DropletBot instrument control."""

    def __init__(self, port: str | None = None, baudrate: int = 115200):
        self._uart = DropletBotUart()
        self._port = port
        self._baudrate = baudrate
        self._baseline: dict[int, float] = {}
        self.cap_cal = CapCalibration()
        if port:
            self.connect(port, baudrate)

    # --- Connection ---

    def connect(self, port: str | None = None, baudrate: int = 115200,
                autodetect: bool = True) -> bool:
        """Connect to the instrument. Logs in to both boards.

        Args:
            port: Serial port path (falls back to the port passed to
                __init__, if any).
            baudrate: Baud rate to try first. Defaults to 115200 (the
                firmware's default for unprovisioned boards); pass the
                board's provisioned app_baud (see uart.set_app_baud()) to
                skip most of the autodetect probing.
            autodetect: If True (default), and login at `baudrate` fails,
                probes the other APP_BAUD_WHITELIST rates (see
                DropletBotUart.init_autodetect()) before giving up. Set
                False to require an exact match at `baudrate` (legacy,
                single-rate behavior).

        After a successful login this also attempts to load a previously
        saved capacitance calibration for this board (see load_cap_cal());
        failure to find/load one is not an error, just no-ops cap_cal.
        """
        p = port or self._port
        if not p:
            raise DropletBotError("No serial port specified")
        self._port = p
        self._baudrate = baudrate
        if autodetect:
            ok, used_baud = self._uart.init_autodetect(p, baudrate)
            if not ok:
                raise DropletBotError(
                    f"Failed to open {p} / login at any of {APP_BAUD_WHITELIST}")
            self._baudrate = used_baud
        else:
            if not self._uart.init(p, baudrate):
                raise DropletBotError(f"Failed to open {p}")
            # Local patch (not in upstream cf15ac0): the same settle +
            # login retry init_autodetect() applies — a freshly opened
            # FTDI/USB-serial port misses the first login reply without
            # it, so the single-rate path never connected over COM-port
            # adapters even at the correct baud.
            time.sleep(0.8)
            if not self._uart.BoardLogin("signal"):
                self._uart.BoardLogin("signal")
        self._uart.BoardLogin("motor")

        if self.load_cap_cal():
            log.info("Cap calibration restored from disk: %s", self.cap_cal)
        else:
            log.info("No persisted cap calibration found; using defaults")
        return True

    def disconnect(self) -> None:
        """Disconnect from the instrument."""
        self._uart.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.disconnect()

    @property
    def connected(self) -> bool:
        return self._uart.sig_board_connected or self._uart.motor_board_connected

    @property
    def uart(self) -> DropletBotUart:
        """Access the underlying low-level driver for advanced operations."""
        return self._uart

    # --- Status ---

    @property
    def status(self) -> dict:
        """Get parsed status from both boards."""
        result = {}
        sig = self._uart.GetBoardStatus("signal")
        if sig and len(sig) >= 34:
            # Local patch (not in upstream cf15ac0): the vendor UI's
            # STATUS decode carries an 18th field, temp_onoff (heater
            # enable), missing here; unpack as many of the known
            # fields as the firmware actually sent.
            fields = [
                "cur_temp", "target_temp", "out_power", "rgy_state",
                "light_led_bright", "flu_led_bright", "chip_on_pad",
                "chip_cap", "chip_short_circuit", "chip_res",
                "dev_temp", "dev_hum", "fan_duty", "pmt",
                "hv_vol", "hv_freq", "cap_match", "temp_onoff",
            ]
            count = min(len(fields), len(sig) // 2)
            values = struct.unpack(f">{count}H", sig[:count * 2])
            result["signal"] = dict(zip(fields[:count], values))
        mot = self._uart.GetBoardStatus("motor")
        if mot and len(mot) >= 7:
            fields = ["rst", "cabin", "mag", "flu", "lpush", "rpush", "pmt"]
            result["motor"] = dict(zip(fields, mot[:7]))
        return result

    @property
    def version(self) -> dict:
        """Get firmware version from both boards."""
        return {
            "signal": self._uart.GetBoardVersion("signal"),
            "motor": self._uart.GetBoardVersion("motor"),
        }

    # --- HV + Electrode Control ---

    def set_actuation(self, voltage_v: float, frequency_hz: int) -> None:
        """Set HV voltage (in volts) and frequency (in Hz) for electrode actuation."""
        # Voltage is sent as integer (firmware interprets as amplitude)
        v_int = max(0, min(int(voltage_v), 255))
        log.debug("Actuation setpoints -> %d V, %d Hz", v_int, frequency_hz)
        self._uart.set_voltage(v_int)
        self._uart.set_frequency(frequency_hz)

    def actuate_channels(self, channels: list[int]) -> None:
        """Activate specific electrode channels (0 to board_channels-1). All others deactivated."""
        n = self._uart.board_channels
        states = np.zeros(n, dtype=bool)
        for ch in channels:
            if 0 <= ch < n:
                states[ch] = True
        log.debug("Actuating %d channel(s): %s", int(states.sum()),
                  sorted(ch for ch in channels if 0 <= ch < n))
        self._uart.setElectrodeStates(states)

    def clear_channels(self) -> None:
        """Deactivate all electrode channels."""
        log.debug("Clearing all electrode channels")
        self._uart.setElectrodeStates(np.zeros(self._uart.board_channels, dtype=bool))

    # --- Capacitance Calibration Persistence ---

    def _cap_cal_key(self) -> str:
        """Board key used for the persisted cap-cal filename.

        The board's STM32 factory UID (see uart.read_uid()) when available;
        falls back to the literal key "default" (old firmware without
        0x1245, or the board unreachable) so a save/load still works, just
        not board-specific.
        """
        uid = self._uart.read_uid()
        return uid if uid else "default"

    def _cap_cal_path(self) -> Path:
        """``~/.dropletbot/cap_cal_<uid-or-default>.json`` for the current board."""
        return Path.home() / ".dropletbot" / f"cap_cal_{self._cap_cal_key()}.json"

    def _cheap_fw_version(self) -> str | None:
        """Best-effort firmware version string for cap-cal save metadata.

        Returns None (silently omitted from the saved JSON) if the signal
        board isn't connected or the version query fails -- this must never
        block or fail a calibration save.
        """
        try:
            version = self._uart.GetBoardVersion("signal")
        except Exception:
            return None
        if not version:
            return None
        return version.get("software_version") or version.get("version")

    def save_cap_cal(self) -> bool:
        """Persist the current ``cap_cal`` (gain, offset_pf) to disk.

        Saved as JSON to ``~/.dropletbot/cap_cal_<uid>.json`` (see
        _cap_cal_path()), alongside a timestamp and, if cheaply available,
        the firmware version. Called automatically by calibrate_capacitance()
        and tare_capacitance() on success; also exposed here for explicit
        use (e.g. after manually constructing a CapCalibration).

        Swallows and logs OSError (e.g. read-only filesystem, permissions)
        rather than raising -- a failed save should never break a
        calibration workflow.

        Returns:
            bool: True if the file was written successfully.
        """
        path = self._cap_cal_path()
        payload = {
            "gain": self.cap_cal.gain,
            "offset_pf": self.cap_cal.offset_pf,
            "timestamp": datetime.now().isoformat(),
        }
        fw_version = self._cheap_fw_version()
        if fw_version is not None:
            payload["fw_version"] = fw_version
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2))
            log.info("Saved cap calibration to %s", path)
            return True
        except OSError as e:
            log.warning("Could not save cap calibration to %s: %s", path, e)
            return False

    def load_cap_cal(self) -> bool:
        """Load a previously persisted ``cap_cal`` (gain, offset_pf) from disk.

        Reads ``~/.dropletbot/cap_cal_<uid>.json`` (see _cap_cal_path()) and,
        on success, replaces ``self.cap_cal`` with a new CapCalibration
        instance (frozen-dataclass semantics preserved -- never mutated in
        place). Called automatically by connect() after login; also exposed
        here for explicit use.

        Returns:
            bool: False (leaving self.cap_cal unchanged) if the file is
            missing, unreadable, or contains invalid/corrupt JSON -- a
            warning is logged specifically in the corrupt/invalid case so
            it's distinguishable from the normal "never calibrated yet"
            missing-file case (info-level only).
        """
        path = self._cap_cal_path()
        if not path.exists():
            log.info("No saved cap calibration at %s", path)
            return False
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Corrupt/unreadable cap calibration file %s: %s", path, e)
            return False
        try:
            gain = float(payload["gain"])
            offset_pf = float(payload["offset_pf"])
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Cap calibration file %s missing/invalid fields: %s", path, e)
            return False
        self.cap_cal = CapCalibration(gain=gain, offset_pf=offset_pf)
        log.info("Loaded cap calibration from %s: gain=%.4f offset_pf=%.4f",
                 path, gain, offset_pf)
        return True

    # --- Capacitance ---

    def calibrate(self) -> dict | None:
        """Run capacitance calibration. Returns {10pf, 100pf, 470pf} values or None."""
        resp = self._uart.calibrateCapacitors()
        if resp and len(resp) >= 6:
            v10, v100, v470 = struct.unpack(">HHH", resp[:6])
            return {"10pf": v10, "100pf": v100, "470pf": v470}
        return None

    def measure_capacitance(
        self, channels: list[int] | None = None, switch_time_ms: int = 20
    ) -> dict[int, int]:
        """Measure capacitance on specified channels (default: all board_channels).

        On a 120-channel board this uses the legacy self-test scan (firmware
        performs its own HV setup). On a board with board_channels > 120 the
        underlying readAllChannels() falls back to the chunked per-channel
        0x1235 scan, which measures with the CURRENT HV/frequency settings
        instead of a self-test ramp -- call set_actuation() (or otherwise
        configure voltage/frequency) before this on a 200-channel board.

        Returns dict mapping channel index to capacitance value.
        """
        n = self._uart.board_channels
        resp = self._uart.readAllChannels(switch_time_ms)
        if resp is None or len(resp) < n:
            return {}
        result = {i: resp[i] for i in range(n)}
        if channels is not None:
            result = {ch: result[ch] for ch in channels if ch in result}
        return result

    def measure_active_capacitance(
        self, n_averages: int = 1, corrected: bool = True
    ) -> float:
        """Measure capacitance of currently active electrodes (fast, single-point).

        Returns capacitance in pF. The firmware uses the DropBot formula
        ``C = amplitude/V_hv * C_cal`` but applies no baseline subtraction; with
        ``corrected=True`` (default) the host ``cap_cal`` (gain + offset) is
        applied: ``(raw - offset_pf) * gain``. Pass ``corrected=False`` for the
        raw firmware value (e.g. while calibrating).
        """
        result = self._uart.measureCapacitance(n_averages)
        raw = result if result is not None else 0.0
        if corrected:
            return (raw - self.cap_cal.offset_pf) * self.cap_cal.gain
        return raw

    def measure_active_capacitance_stats(
        self, n_averages: int = 1, corrected: bool = True
    ) -> dict | None:
        """Measure active-electrode capacitance with signal-quality statistics.

        Returns the full measurement: cap_pf plus proportion, mode, n_total,
        n_high, n_low, n_dropped, elapsed_us. Returns None on failure. With
        ``corrected=True`` the returned ``cap_pf`` has the host ``cap_cal``
        applied and the original is preserved as ``cap_pf_raw``.
        """
        result = self._uart.measureCapacitanceFull(n_averages)
        if result is None:
            return None
        raw = result.get("cap_pf", 0.0)
        result["cap_pf_raw"] = raw
        if corrected:
            result["cap_pf"] = (raw - self.cap_cal.offset_pf) * self.cap_cal.gain
        return result

    def tare_capacitance(self, n_averages: int = 8) -> float:
        """Zero the capacitance baseline at the current electrode state.

        Measures the raw capacitance with whatever electrodes are presently
        active (call with the chip dry / empty) and stores it as
        ``cap_cal.offset_pf``, keeping the existing gain. Returns the raw pF.
        This is the DropBot-style baseline: subsequent corrected readings report
        the change relative to this reference. On success, the updated
        cap_cal is auto-saved to disk (see save_cap_cal()), keyed by board UID.
        """
        raw = self.measure_active_capacitance(n_averages, corrected=False)
        self.cap_cal = CapCalibration(gain=self.cap_cal.gain, offset_pf=raw)
        log.info("Capacitance baseline tared: offset_pf=%.3f (gain=%.4f kept)",
                 raw, self.cap_cal.gain)
        self.save_cap_cal()
        return raw

    def calibrate_capacitance(
        self,
        pf_per_electrode: float = 10.0,
        channels: list[int] | None = None,
        n_averages: int = 8,
        settle_s: float = 0.3,
    ) -> dict:
        """Calibrate host gain + offset against a known reference board.

        Sweeps an increasing number of reference electrodes (each contributing
        ``pf_per_electrode``), linear-fits ``raw = slope * N + intercept``, then
        sets ``gain = pf_per_electrode / slope`` and ``offset_pf = intercept`` so
        that corrected capacitance reads ``pf_per_electrode * N``. The gain
        (the firmware ``C_cal`` scale correction) is board-independent and worth
        keeping; re-run :meth:`tare_capacitance` on the real chip to refresh the
        offset. Returns ``{gain, offset_pf, slope_raw, r2}``. On success, the
        updated cap_cal is auto-saved to disk (see save_cap_cal()), keyed by
        board UID.
        """
        if channels is None:
            channels = list(range(8))
        ns: list[int] = []
        raws: list[float] = []
        for k in range(1, len(channels) + 1):
            self.actuate_channels(channels[:k])
            time.sleep(settle_s)
            raws.append(self.measure_active_capacitance(n_averages, corrected=False))
            ns.append(k)
        n = np.asarray(ns, dtype=float)
        y = np.asarray(raws, dtype=float)
        slope, intercept = np.polyfit(n, y, 1)
        gain = pf_per_electrode / slope if slope else 1.0
        self.cap_cal = CapCalibration(gain=float(gain), offset_pf=float(intercept))
        log.info("Capacitance calibrated: gain=%.4f offset_pf=%.3f "
                 "(slope=%.3f over %d points)",
                 float(gain), float(intercept), float(slope), len(ns))
        self.save_cap_cal()
        pred = slope * n + intercept
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
        return {
            "gain": float(gain),
            "offset_pf": float(intercept),
            "slope_raw": float(slope),
            "r2": r2,
        }

    # --- Temperature ---

    def set_temperature(
        self, target_c: float, enable: bool = True, channel: int = 0
    ) -> None:
        """Set heater target temperature and enable/disable control.

        Args:
            target_c: Target temperature in degrees Celsius.
            enable: True to start heating, False to stop.
            channel: Heater channel (0 or 1).
        """
        log.debug("Heater ch%d -> %.2f C, control %s", channel, target_c,
                  "on" if enable else "off")
        self._uart.set_temp_target(target_c, channel=channel)
        self._uart.set_temp_control(enable, channel=channel)

    def stop_heater(self, channel: int = 0) -> None:
        """Disable heater on specified channel."""
        self._uart.set_temp_control(False, channel=channel)

    def get_temperature(self, channel: int = 0) -> dict | None:
        """Read current temperature info.

        Args:
            channel: Heater channel (0 or 1).

        Returns:
            Dict with current_c, target_c, output_pct or None.
        """
        info = self._uart.get_temp_info(channel=channel)
        if info:
            return {"current_c": info[0], "target_c": info[1], "output_pct": info[2]}
        return None

    def get_temp_params(self, channel: int = 0) -> dict | None:
        """Read PID parameters for a heater channel."""
        return self._uart.get_temp_params(channel=channel)

    # --- Motor Control ---

    def home_all(self) -> None:
        """Home all motor axes (chip tray + magnet, pogo plates, filter, PMT)."""
        log.info("Homing all motor axes (tray+magnet, pogo, filter, PMT)")
        self._uart.resetChipTrayAndMagnet()
        self._uart.resetPogoPlates()
        self._uart.resetFluorescenceFilter()
        self._uart.resetPMTMotor()
        log.info("Home-all sequence finished")

    def move_tray(self, position: str) -> bool | None:
        """Move chip tray. position: 'in' (0), 'out' (1).

        If the magnet is engaged, it will be automatically disengaged
        before moving the tray.
        """
        states = {"in": 0, "out": 1}
        if position not in states:
            raise DropletBotError(f"Invalid tray position: {position}")

        result = self._uart.setTray(states[position])

        # If tray move failed, check if magnet is blocking
        if not result or result == b'' or result is False:
            mot_status = self._uart.GetBoardStatus("motor")
            if mot_status and len(mot_status) >= 3:
                mag_state = mot_status[2]  # mag field
                if mag_state == 0x01:  # MAG_STATE_ENGAGED
                    log.warning("Magnet engaged — auto-disengaging before tray move")
                    self.move_magnet("disengage")
                    time.sleep(1)
                    result = self._uart.setTray(states[position])

        return result

    def move_magnet(self, position: str) -> bool | None:
        """Move magnet. position: 'engage' (1), 'disengage' (0)."""
        states = {"engage": 1, "disengage": 0, "press": 1, "release": 0}
        if position not in states:
            raise DropletBotError(f"Invalid magnet position: {position}")
        return self._uart.setMagnet(states[position])

    # --- Detection ---

    def detect_shorts(self) -> tuple[bool, bool]:
        """Detect chip presence and short circuits.

        Returns (chip_loaded, short_detected).
        """
        resp = self._uart.detect_shorts()
        if resp and len(resp) >= 2:
            return (bool(resp[0]), bool(resp[1]))
        return (False, False)

    # --- Event Streaming ---

    def enable_streaming(
        self, mask: int = SignalBoard.EVT_ALL, interval_ms: int = 1000
    ) -> None:
        """Enable event streaming with given mask and interval."""
        log.debug("Event streaming enabled: mask=0x%08X interval=%d ms",
                  mask, interval_ms)
        self._uart.set_event_mask(mask)
        self._uart.set_report_interval(interval_ms)

    def disable_streaming(self) -> None:
        """Disable event streaming."""
        log.debug("Event streaming disabled")
        self._uart.set_event_mask(0)

    # --- Safety ---

    def clear_alarm(self, board: str, code: str) -> bool:
        """Clear/confirm an alarm by its 5-character code."""
        return self._uart.clearAlarm(board, code)

    # --- Fan & Power ---

    def set_fan(self, on: bool, board: str = "motor") -> bool:
        """Control fan. 'motor' = instrument fans, 'signal' = MCU board fan."""
        return self._uart.setFan(on, board=board)

    def set_buzzer(self, on: bool) -> bool:
        """Control buzzer."""
        return self._uart.setBuzzer(on)

    # --- Electrode Self-Test ---

    def self_test_electrodes(
        self, switch_time_ms: int = 20,
        thresholds: dict[str, tuple[int, int]] | None = None,
    ) -> dict[int, dict]:
        """Test all board_channels electrode channels for expected capacitance.

        Args:
            switch_time_ms: Settle time per channel during scan.
            thresholds: Override pass/fail ranges per group.
                Default: {"470pf": (3, 40), "100pf": (3, 30), "10pf": (1, 20)}

        Returns:
            Dict mapping channel → {value, group, range, passed}.
        """
        if thresholds is None:
            thresholds = {"470pf": (3, 40), "100pf": (3, 30), "10pf": (1, 20)}

        raw = self.measure_capacitance(switch_time_ms=switch_time_ms)
        if not raw:
            raise DropletBotError("Capacitance scan returned no data")

        results = {}
        for ch in range(self._uart.board_channels):
            value = raw.get(ch, 0)
            if ch in _CAP_470PF_CHANNELS:
                group = "470pf"
            elif ch in _CAP_100PF_CHANNELS:
                group = "100pf"
            else:
                group = "10pf"
            lo, hi = thresholds[group]
            results[ch] = {
                "value": value,
                "group": group,
                "range": (lo, hi),
                "passed": lo <= value <= hi,
            }
        return results

    # --- Voltage Ramping ---

    def ramp_voltage(
        self, target_v: float, start_v: float | None = None,
        step_v: float = 5.0, delay_s: float = 0.05,
    ) -> None:
        """Gradually ramp HV voltage to target to avoid electrowetting stress.

        Args:
            target_v: Target voltage (0-255).
            start_v: Starting voltage. If None, ramps from 0.
            step_v: Voltage increment per step.
            delay_s: Delay between steps in seconds.
        """
        current = start_v if start_v is not None else 0
        target = max(0, min(int(target_v), 255))
        step = abs(step_v)

        if current < target:
            v = current + step
            while v < target:
                self._uart.set_voltage(int(v))
                time.sleep(delay_s)
                v += step
        elif current > target:
            v = current - step
            while v > target:
                self._uart.set_voltage(int(v))
                time.sleep(delay_s)
                v -= step

        self._uart.set_voltage(target)

    # --- Drop Detection ---

    def calibrate_baseline(self, switch_time_ms: int = 20) -> dict[int, float]:
        """Measure capacitance baseline with no drops present.

        Call this with a clean chip (no drops) to establish reference values.
        Results are stored internally for use by detect_drops().

        Returns:
            Dict mapping channel → baseline capacitance value.
        """
        self._baseline = self.measure_capacitance(switch_time_ms=switch_time_ms)
        log.info("Baseline calibrated: %d channels", len(self._baseline))
        return dict(self._baseline)

    def detect_drops(
        self,
        channels: list[int] | None = None,
        threshold_pf: float = 5.0,
        switch_time_ms: int = 20,
    ) -> dict[int, bool]:
        """Detect droplet presence by comparing current cap to baseline.

        Args:
            channels: Channels to check (default: all with baseline data).
            threshold_pf: Minimum delta above baseline to flag as drop present.
            switch_time_ms: Settle time per channel.

        Returns:
            Dict mapping channel → True if drop detected.

        Raises:
            DropletBotError: If no baseline has been calibrated.
        """
        if not self._baseline:
            raise DropletBotError("No baseline — call calibrate_baseline() first")

        current = self.measure_capacitance(
            channels=channels, switch_time_ms=switch_time_ms
        )
        check_channels = channels if channels is not None else list(self._baseline.keys())

        result = {}
        for ch in check_channels:
            if ch in current and ch in self._baseline:
                delta = current[ch] - self._baseline[ch]
                result[ch] = delta >= threshold_pf
        return result

    # --- Feedback-Controlled Actuation ---

    def actuate_and_verify(
        self,
        channels: list[int],
        expected_pf: float = 10.0,
        max_retries: int = 3,
        voltage_step_v: float = 10.0,
        initial_voltage_v: float = 50.0,
        frequency_hz: int = 10000,
    ) -> bool:
        """Actuate channels and verify via capacitance measurement.

        Activates the given channels, measures capacitance, and if below
        the expected threshold, increases voltage and retries.

        Args:
            channels: Electrode channels to actuate.
            expected_pf: Minimum capacitance (pF) to consider successful.
            max_retries: Maximum voltage increase attempts.
            voltage_step_v: Voltage increase per retry.
            initial_voltage_v: Starting voltage.
            frequency_hz: Actuation frequency.

        Returns:
            True if all channels meet the expected capacitance threshold.
        """
        voltage = initial_voltage_v
        self._uart.set_frequency(frequency_hz)

        for attempt in range(max_retries + 1):
            self.ramp_voltage(voltage)
            self.actuate_channels(channels)
            time.sleep(0.1)  # settle

            cap = self.measure_active_capacitance(n_averages=3)
            all_ok = cap >= expected_pf

            log.info(
                "Attempt %d/%d @ %.0fV: %.1f pF (need %.1f)",
                attempt + 1, max_retries + 1, voltage, cap, expected_pf,
            )

            if all_ok:
                return True

            voltage = min(voltage + voltage_step_v, 255)

        self.clear_channels()
        return False

    # --- Frequency Sweep ---

    def frequency_sweep(
        self,
        channels: list[int],
        freqs: list[int] | None = None,
        voltage_v: float = 100,
        settle_s: float = 0.1,
    ) -> dict[int, float]:
        """Sweep frequency and measure capacitance at each point.

        Args:
            channels: Channels to actuate during sweep.
            freqs: Frequencies to test (Hz). Default: [100..100000].
            voltage_v: Actuation voltage.
            settle_s: Settle time after frequency change.

        Returns:
            Dict mapping frequency (Hz) → mean capacitance (pF).
        """
        if freqs is None:
            freqs = [100, 500, 1000, 5000, 10000, 20000, 50000, 100000]

        # Save current state
        orig_freq = self._uart.frequency or 10000

        self.ramp_voltage(voltage_v)
        self.actuate_channels(channels)
        time.sleep(0.1)

        results = {}
        for freq in freqs:
            self._uart.set_frequency(freq)
            time.sleep(settle_s)
            cap = self.measure_active_capacitance(n_averages=3)
            results[freq] = cap
            log.info("Sweep %d Hz: %.1f pF", freq, cap)

        # Restore
        self._uart.set_frequency(orig_freq)
        self.clear_channels()

        return results
