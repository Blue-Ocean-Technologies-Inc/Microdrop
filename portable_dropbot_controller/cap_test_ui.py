#!/usr/bin/env python3
"""Interactive capacitance test UI for DropletBot.

Controls: tray in/out, pogo press/release, magnet engage/disengage
Capacitance: single-point measurement, full 120-channel scan,
             self-test, voltage ramp, frequency sweep, calibration
"""

import os
import sys
import time
import struct
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime

import numpy as np

# Allow running this script directly: put the package parent on sys.path and
# import the driver via the installed package (falling back to flat imports
# when run from inside the package directory).
_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)
try:
    from portable_dropbot_controller.session import DropletBotSession
    from portable_dropbot_controller.portable_dropbot_service import DropletBotUart
except ImportError:
    from session import DropletBotSession
    from portable_dropbot_service import DropletBotUart

# Default serial port; override with the DROPBOT_PORT env var, a CLI argument,
# or the port entry field in the UI.
PORT = os.environ.get(
    "DROPBOT_PORT",
    sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbserial-FT94O7N7",
)


class CapTestUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DropletBot — Capacitance Test")
        self.root.geometry("900x700")

        self.bot: DropletBotSession | None = None
        self._connected = False

        self._build_ui()
        self._log("Ready. Click Connect.")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # Top bar: connection
        conn = ttk.Frame(self.root)
        conn.pack(fill=tk.X, padx=5, pady=3)
        self.port_var = tk.StringVar(value=PORT)
        ttk.Label(conn, text="Port:").pack(side=tk.LEFT)
        ttk.Entry(conn, textvariable=self.port_var, width=28).pack(side=tk.LEFT, padx=3)
        self.btn_connect = ttk.Button(conn, text="Connect", command=self._on_connect)
        self.btn_connect.pack(side=tk.LEFT, padx=3)
        self.lbl_status = ttk.Label(conn, text="Disconnected", foreground="red")
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # --- Mechanism controls ---
        mech = ttk.LabelFrame(self.root, text="Mechanism")
        mech.pack(fill=tk.X, padx=5, pady=3)

        row1 = ttk.Frame(mech)
        row1.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(row1, text="Home All", command=lambda: self._run(self._home_all)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Tray IN", command=lambda: self._run(self._tray_in)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Tray OUT", command=lambda: self._run(self._tray_out)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Pogo Press", command=lambda: self._run(self._pogo_press)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Pogo Release", command=lambda: self._run(self._pogo_release)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Mag Engage", command=lambda: self._run(self._mag_engage)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Mag Disengage", command=lambda: self._run(self._mag_disengage)).pack(side=tk.LEFT, padx=2)

        # --- HV controls ---
        hv = ttk.LabelFrame(self.root, text="HV / Frequency")
        hv.pack(fill=tk.X, padx=5, pady=3)

        row2 = ttk.Frame(hv)
        row2.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row2, text="Voltage:").pack(side=tk.LEFT)
        self.voltage_var = tk.IntVar(value=100)
        ttk.Scale(row2, from_=0, to=200, variable=self.voltage_var, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=3)
        self.lbl_voltage = ttk.Label(row2, text="100")
        self.lbl_voltage.pack(side=tk.LEFT)
        self.voltage_var.trace_add("write", lambda *_: self.lbl_voltage.config(text=str(self.voltage_var.get())))

        ttk.Label(row2, text="  Freq (Hz):").pack(side=tk.LEFT, padx=(15, 0))
        self.freq_var = tk.IntVar(value=10000)
        ttk.Entry(row2, textvariable=self.freq_var, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2, text="Set HV", command=lambda: self._run(self._set_hv)).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="HV OFF", command=lambda: self._run(self._hv_off)).pack(side=tk.LEFT, padx=2)

        # --- Capacitance controls ---
        cap = ttk.LabelFrame(self.root, text="Capacitance")
        cap.pack(fill=tk.X, padx=5, pady=3)

        row3 = ttk.Frame(cap)
        row3.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row3, text="Channel:").pack(side=tk.LEFT)
        self.channel_var = tk.IntVar(value=0)
        ttk.Spinbox(row3, from_=0, to=119, textvariable=self.channel_var, width=5).pack(side=tk.LEFT, padx=3)
        ttk.Label(row3, text="Averages:").pack(side=tk.LEFT, padx=(10, 0))
        self.avg_var = tk.IntVar(value=5)
        ttk.Spinbox(row3, from_=1, to=50, textvariable=self.avg_var, width=4).pack(side=tk.LEFT, padx=3)

        ttk.Button(row3, text="Measure Ch", command=lambda: self._run(self._measure_single)).pack(side=tk.LEFT, padx=5)
        ttk.Button(row3, text="Measure Active", command=lambda: self._run(self._measure_active)).pack(side=tk.LEFT, padx=2)

        row4 = ttk.Frame(cap)
        row4.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(row4, text="Self-Test (120ch)", command=lambda: self._run(self._self_test)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row4, text="Calibrate", command=lambda: self._run(self._calibrate)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row4, text="Freq Sweep", command=lambda: self._run(self._freq_sweep)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row4, text="Cumulative Test", command=lambda: self._run(self._cumulative_test)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row4, text="Read ADC Raw", command=lambda: self._run(self._read_adc_raw)).pack(side=tk.LEFT, padx=2)

        # --- Electrode control ---
        elec = ttk.LabelFrame(self.root, text="Electrodes")
        elec.pack(fill=tk.X, padx=5, pady=3)

        row5 = ttk.Frame(elec)
        row5.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row5, text="Channels (comma-sep):").pack(side=tk.LEFT)
        self.electrodes_var = tk.StringVar(value="0")
        ttk.Entry(row5, textvariable=self.electrodes_var, width=30).pack(side=tk.LEFT, padx=3)
        ttk.Button(row5, text="Activate", command=lambda: self._run(self._activate_electrodes)).pack(side=tk.LEFT, padx=3)
        ttk.Button(row5, text="Clear All", command=lambda: self._run(self._clear_electrodes)).pack(side=tk.LEFT, padx=2)

        # --- Log ---
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Courier", 11))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

    # ------------------------------------------------------------------ Logging
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.root.after(0, lambda: self._log_insert(f"[{ts}] {msg}"))

    def _log_insert(self, msg: str):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    # ------------------------------------------------------------------ Threading
    def _run(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    # ------------------------------------------------------------------ Connection
    def _on_connect(self):
        if self._connected:
            self.bot.disconnect()
            self._connected = False
            self.lbl_status.config(text="Disconnected", foreground="red")
            self.btn_connect.config(text="Connect")
            self._log("Disconnected")
            return
        self._run(self._do_connect)

    def _do_connect(self):
        port = self.port_var.get()
        self._log(f"Connecting to {port}...")
        try:
            self.bot = DropletBotSession()
            self.bot.connect(port)
            time.sleep(1)
            self._connected = True
            v = self.bot.version
            self.root.after(0, lambda: self.lbl_status.config(text="Connected", foreground="green"))
            self.root.after(0, lambda: self.btn_connect.config(text="Disconnect"))
            self._log(f"Connected: {v.get('signal', {})}")
            self._log(f"Motor: {v.get('motor', {})}")
        except Exception as e:
            self._log(f"Connect failed: {e}")

    def _check(self) -> bool:
        if not self._connected or not self.bot:
            self._log("Not connected")
            return False
        return True

    # ------------------------------------------------------------------ Mechanism
    def _home_all(self):
        if not self._check(): return
        self._log("Homing tray + magnet...")
        self.bot.uart.resetChipTrayAndMagnet()
        self._log("Homing pogo plates...")
        self.bot.uart.resetPogoPlates()
        self._log("Home complete")

    def _tray_in(self):
        if not self._check(): return
        self._log("Tray IN...")
        self.bot.move_tray("in")
        self._log("Tray IN done")

    def _tray_out(self):
        if not self._check(): return
        self._log("Tray OUT...")
        self.bot.move_tray("out")
        self._log("Tray OUT done")

    def _pogo_press(self):
        if not self._check(): return
        self._log("Pogo press...")
        self.bot.uart.setPogo(1)
        self._log("Pogo pressed")

    def _pogo_release(self):
        if not self._check(): return
        self._log("Pogo release...")
        self.bot.uart.setPogo(0)
        self._log("Pogo released")

    def _mag_engage(self):
        if not self._check(): return
        self._log("Magnet engage...")
        self.bot.move_magnet("engage")
        self._log("Magnet engaged")

    def _mag_disengage(self):
        if not self._check(): return
        self._log("Magnet disengage...")
        self.bot.move_magnet("disengage")
        self._log("Magnet disengaged")

    # ------------------------------------------------------------------ HV
    def _set_hv(self):
        if not self._check(): return
        v = self.voltage_var.get()
        f = self.freq_var.get()
        self.bot.set_actuation(voltage_v=v, frequency_hz=f)
        self._log(f"HV set: {v}V @ {f} Hz")

    def _hv_off(self):
        if not self._check(): return
        self.bot.uart.set_voltage(0)
        self._log("HV OFF")

    # ------------------------------------------------------------------ Electrodes
    def _activate_electrodes(self):
        if not self._check(): return
        try:
            channels = [int(x.strip()) for x in self.electrodes_var.get().split(",") if x.strip()]
            self.bot.actuate_channels(channels)
            self._log(f"Activated channels: {channels}")
        except ValueError:
            self._log("Invalid channel list")

    def _clear_electrodes(self):
        if not self._check(): return
        self.bot.clear_channels()
        self._log("All electrodes cleared")

    # ------------------------------------------------------------------ Capacitance
    def _measure_single(self):
        if not self._check(): return
        ch = self.channel_var.get()
        n = self.avg_var.get()
        self._log(f"Measuring ch{ch} (n={n})...")
        self.bot.actuate_channels([ch])
        time.sleep(0.15)
        cap = self.bot.measure_active_capacitance(n_averages=n)
        self.bot.clear_channels()
        self._log(f"  ch{ch}: {cap:.2f} pF")

    def _measure_active(self):
        if not self._check(): return
        n = self.avg_var.get()
        cap = self.bot.measure_active_capacitance(n_averages=n)
        self._log(f"Active electrodes: {cap:.2f} pF")

    def _self_test(self):
        if not self._check(): return
        self._log("Running 120-channel self-test...")
        results = self.bot.self_test_electrodes(switch_time_ms=10)
        passed = sum(1 for r in results.values() if r['passed'])
        self._log(f"Result: {passed}/120 passed")

        groups = {'10pf': [], '100pf': [], '470pf': []}
        for r in results.values():
            groups[r['group']].append(r['value'])
        for g, vals in groups.items():
            avg = sum(vals) / len(vals) if vals else 0
            self._log(f"  {g:5s}: n={len(vals):3d}, avg={avg:.1f}, min={min(vals)}, max={max(vals)}")

        failed = [(ch, results[ch]) for ch in range(120) if not results[ch]['passed']]
        if failed:
            for ch, r in failed[:10]:
                self._log(f"  FAIL ch{ch}: {r['value']} ({r['group']}, range {r['range']})")

    def _calibrate(self):
        if not self._check(): return
        self._log("Running calibration...")
        cal = self.bot.calibrate()
        if cal:
            self._log(f"Calibration: {cal}")
        else:
            self._log("Calibration failed or timed out")

    def _freq_sweep(self):
        if not self._check(): return
        ch_text = self.electrodes_var.get()
        try:
            channels = [int(x.strip()) for x in ch_text.split(",") if x.strip()]
        except ValueError:
            channels = [0]
        v = self.voltage_var.get()
        self._log(f"Frequency sweep ch{channels} @ {v}V...")
        sweep = self.bot.frequency_sweep(
            channels, freqs=[100, 500, 1000, 5000, 10000, 20000, 50000, 100000],
            voltage_v=v, settle_s=0.1,
        )
        for freq, cap in sweep.items():
            self._log(f"  {freq:6d} Hz: {cap:.2f} pF")
        self.bot.ramp_voltage(0)

    def _cumulative_test(self):
        if not self._check(): return
        v = self.voltage_var.get()
        self._log(f"Cumulative cap test @ {v}V...")
        self.bot.set_actuation(voltage_v=v, frequency_hz=self.freq_var.get())
        time.sleep(0.3)

        active = []
        checkpoints = [1, 2, 5, 10, 20, 40, 60, 80, 100, 120]
        ch = 0
        self._log(f"{'N':>4s}  {'Expected':>8s}  {'Measured':>8s}  {'Err':>6s}")
        for target in checkpoints:
            while len(active) < target and ch < 120:
                active.append(ch)
                ch += 1
            self.bot.actuate_channels(active)
            time.sleep(0.15)
            cap = self.bot.measure_active_capacitance(n_averages=5)
            expected = len(active) * 10.0
            err = ((cap - expected) / expected * 100) if expected > 0 else 0
            self._log(f"{len(active):4d}  {expected:6.0f} pF  {cap:6.1f} pF  {err:+5.1f}%")
        self.bot.clear_channels()
        self.bot.ramp_voltage(0)

    def _read_adc_raw(self):
        if not self._check(): return
        self._log("Reading ADC channels...")
        # CMD_READ_ADC_DATA (0x12A5) reads all 8 ADC128 channels
        cmd = 0x12A5
        pkt = self.bot.uart._make_cmd_packet(cmd)
        resp = self.bot.uart._wr(pkt, cmd, timeout_s=3)
        if resp and len(resp) >= 16:
            vals = struct.unpack('>8H', resp[:16])
            names = ['CH0', 'CH1', 'CH2', 'CH3', 'CH4', 'CH5', 'CH6', 'CH7']
            for n, v in zip(names, vals):
                voltage = v / 100.0
                self._log(f"  {n}: {v:5d} raw ({voltage:.2f} V)")
        else:
            self._log(f"ADC read failed: {resp}")


def main():
    root = tk.Tk()
    app = CapTestUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
