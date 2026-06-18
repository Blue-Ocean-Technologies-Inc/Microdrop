"""High-level DropletBot session API.

Wraps the low-level PortableDropbotService (DropletBotUart) with a
clean, Pythonic interface. Supports context manager usage::

    with DropletBotSession("/dev/ttyUSB0") as bot:
        bot.set_actuation(voltage_v=100, frequency_hz=10000)
        bot.actuate_channels([0, 1, 5, 10])
        caps = bot.measure_capacitance()
        print(caps)
"""

import logging
import struct
import time

import numpy as np

from .portable_dropbot_service import DropletBotUart
from .commands import SignalBoard, MotorBoard

log = logging.getLogger(__name__)

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
        if port:
            self.connect(port, baudrate)

    # --- Connection ---

    def connect(self, port: str | None = None, baudrate: int = 115200) -> bool:
        """Connect to the instrument. Logs in to both boards."""
        p = port or self._port
        if not p:
            raise DropletBotError("No serial port specified")
        self._port = p
        self._baudrate = baudrate
        if not self._uart.init(p, baudrate):
            raise DropletBotError(f"Failed to open {p}")
        self._uart.BoardLogin("signal")
        self._uart.BoardLogin("motor")
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
            fields = [
                "cur_temp", "target_temp", "out_power", "rgy_state",
                "light_led_bright", "flu_led_bright", "chip_on_pad",
                "chip_cap", "chip_short_circuit", "chip_res",
                "dev_temp", "dev_hum", "fan_duty", "pmt",
                "hv_vol", "hv_freq", "cap_match",
            ]
            values = struct.unpack(f">{len(fields)}H", sig[:len(fields) * 2])
            result["signal"] = dict(zip(fields, values))
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
        self._uart.set_voltage(v_int)
        self._uart.set_frequency(frequency_hz)

    def actuate_channels(self, channels: list[int]) -> None:
        """Activate specific electrode channels (0-119). All others deactivated."""
        states = np.zeros(120, dtype=bool)
        for ch in channels:
            if 0 <= ch < 120:
                states[ch] = True
        self._uart.setElectrodeStates(states)

    def clear_channels(self) -> None:
        """Deactivate all electrode channels."""
        self._uart.setElectrodeStates(np.zeros(120, dtype=bool))

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
        """Measure capacitance on specified channels (default: all 120).

        Returns dict mapping channel index to capacitance value.
        """
        resp = self._uart.readAllChannels(switch_time_ms)
        if resp is None or len(resp) < 120:
            return {}
        result = {i: resp[i] for i in range(120)}
        if channels is not None:
            result = {ch: result[ch] for ch in channels if ch in result}
        return result

    def measure_active_capacitance(self, n_averages: int = 1) -> float:
        """Measure capacitance of currently active electrodes (fast, single-point).

        Returns capacitance in pF. Uses firmware's DropBot formula.
        """
        result = self._uart.measureCapacitance(n_averages)
        return result if result is not None else 0.0

    def measure_active_capacitance_stats(self, n_averages: int = 1) -> dict | None:
        """Measure active-electrode capacitance with signal-quality statistics.

        Returns the full measurement: cap_pf plus proportion, mode, n_total,
        n_high, n_low, n_dropped, elapsed_us. Returns None on failure.
        """
        return self._uart.measureCapacitanceFull(n_averages)

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
        self._uart.resetChipTrayAndMagnet()
        self._uart.resetPogoPlates()
        self._uart.resetFluorescenceFilter()
        self._uart.resetPMTMotor()

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
        self._uart.set_event_mask(mask)
        self._uart.set_report_interval(interval_ms)

    def disable_streaming(self) -> None:
        """Disable event streaming."""
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
        """Test all 120 electrode channels for expected capacitance.

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
        for ch in range(120):
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
