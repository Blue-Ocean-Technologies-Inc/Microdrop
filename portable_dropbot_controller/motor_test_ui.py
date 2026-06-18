#!/usr/bin/env python3
"""Interactive motor test UI for DropletBot.

Motor IDs (from smt_init.c):
  0 = Chip Tray (cabin)
  1 = PMT Y-axis
  2 = Magnet Z-axis
  3 = Fluorescence filter
  4 = Pogo Right
  5 = Pogo Left

Protocol directions (from Qt debug tool):
  Cabin:  0=IN, 1=OUT
  Magnet: 0=disengage, 1=engage
  Pogo:   0=press, 1=release
"""

import sys
import os
import time
import struct
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime

# Allow running this script directly: put the package parent on sys.path and
# import the driver via the installed package (falling back to flat imports
# when run from inside the package directory).
_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)
try:
    from portable_dropbot_controller.proxy import SignalBoardProxy, MotorBoardProxy
    from portable_dropbot_controller.portable_dropbot_service import DropletBotUart
except ImportError:
    from proxy import SignalBoardProxy, MotorBoardProxy
    from portable_dropbot_service import DropletBotUart

# Default serial port; override with the DROPBOT_PORT env var or a CLI argument.
PORT = os.environ.get(
    "DROPBOT_PORT",
    sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbserial-FT94O7N7",
)

# Motor IDs
MT_CABIN  = 0
MT_PMT    = 1
MT_MAG_Z  = 2
MT_FLU    = 3
MT_POGO_R = 4
MT_POGO_L = 5

# Motor actions
MT_ABSOLUTE = 0
MT_RELATIVE = 1
MT_STOP     = 3
MT_HOME     = 4


class MotorTestUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DropletBot Motor Test")
        self.root.geometry("780x900")

        self.uart = None
        self.proxy = None
        self.drv = None
        self.connected = False

        self._build_ui()

    def _build_ui(self):
        # Connection
        conn = ttk.LabelFrame(self.root, text="Connection", padding=10)
        conn.pack(fill="x", padx=10, pady=3)
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(conn, textvariable=self.status_var, font=("Menlo", 11)).pack(side="left")
        ttk.Button(conn, text="Connect", command=self._connect_async).pack(side="right")
        ttk.Button(conn, text="Connect + Home", command=lambda: self._connect_async(home=True)).pack(side="right", padx=3)
        ttk.Button(conn, text="Disconnect", command=self._disconnect).pack(side="right", padx=5)

        # Chip Tray
        tray = ttk.LabelFrame(self.root, text="Chip Tray (motor 0)", padding=8)
        tray.pack(fill="x", padx=10, pady=3)
        ttk.Button(tray, text="Home", command=lambda: self._cmd("tray_home"), width=12).pack(side="left", padx=3)
        ttk.Button(tray, text="OUT", command=lambda: self._cmd("tray_out"), width=12).pack(side="left", padx=3)
        ttk.Button(tray, text="IN", command=lambda: self._cmd("tray_in"), width=12).pack(side="left", padx=3)
        ttk.Button(tray, text="Read", command=lambda: self._cmd("tray_read"), width=12).pack(side="left", padx=3)

        # Pogo Pins (L/R swapped on this HW: button "Home L" → motor 4, "Home R" → motor 5)
        pogo = ttk.LabelFrame(self.root, text="Pogo Pins (motors 4+5)", padding=8)
        pogo.pack(fill="x", padx=10, pady=3)
        ttk.Button(pogo, text="Home Both", command=lambda: self._cmd("pogo_home"), width=12).pack(side="left", padx=3)
        ttk.Button(pogo, text="Home L", command=lambda: self._cmd("pogo_home_l"), width=8).pack(side="left", padx=2)
        ttk.Button(pogo, text="Home R", command=lambda: self._cmd("pogo_home_r"), width=8).pack(side="left", padx=2)
        ttk.Button(pogo, text="Press", command=lambda: self._cmd("pogo_press"), width=12).pack(side="left", padx=3)
        ttk.Button(pogo, text="Release", command=lambda: self._cmd("pogo_release"), width=12).pack(side="left", padx=3)
        ttk.Button(pogo, text="Read", command=lambda: self._cmd("pogo_read"), width=12).pack(side="left", padx=3)

        # Magnet
        mag = ttk.LabelFrame(self.root, text="Magnet Z (motor 2)", padding=8)
        mag.pack(fill="x", padx=10, pady=3)
        ttk.Button(mag, text="Home", command=lambda: self._cmd("mag_home"), width=12).pack(side="left", padx=3)
        ttk.Button(mag, text="Engage", command=lambda: self._cmd("mag_engage"), width=12).pack(side="left", padx=3)
        ttk.Button(mag, text="Disengage", command=lambda: self._cmd("mag_disengage"), width=12).pack(side="left", padx=3)
        ttk.Button(mag, text="Read", command=lambda: self._cmd("mag_read"), width=12).pack(side="left", padx=3)

        # Fluorescence Filter
        flu = ttk.LabelFrame(self.root, text="Fluorescence Filter (motor 3)", padding=8)
        flu.pack(fill="x", padx=10, pady=3)
        ttk.Button(flu, text="Home", command=lambda: self._cmd("flu_home"), width=12).pack(side="left", padx=3)
        for i in range(1, 6):
            ttk.Button(flu, text=f"Pos {i}", command=lambda p=i: self._cmd(f"flu_{p}"), width=7).pack(side="left", padx=2)
        ttk.Button(flu, text="Read", command=lambda: self._cmd("flu_read"), width=12).pack(side="left", padx=3)

        # PMT
        pmt = ttk.LabelFrame(self.root, text="PMT Motor (motor 1)", padding=8)
        pmt.pack(fill="x", padx=10, pady=3)
        ttk.Button(pmt, text="Home", command=lambda: self._cmd("pmt_home"), width=12).pack(side="left", padx=3)
        for i in range(1, 6):
            ttk.Button(pmt, text=f"Pos {i}", command=lambda p=i: self._cmd(f"pmt_{p}"), width=7).pack(side="left", padx=2)
        ttk.Button(pmt, text="Read", command=lambda: self._cmd("pmt_read"), width=12).pack(side="left", padx=3)

        # LEDs
        led = ttk.LabelFrame(self.root, text="LEDs", padding=8)
        led.pack(fill="x", padx=10, pady=3)
        ttk.Button(led, text="RGB Off", command=lambda: self._cmd("rgb_off"), width=9).pack(side="left", padx=2)
        ttk.Button(led, text="Red", command=lambda: self._cmd("rgb_red"), width=7).pack(side="left", padx=2)
        ttk.Button(led, text="Green", command=lambda: self._cmd("rgb_green"), width=7).pack(side="left", padx=2)
        ttk.Button(led, text="Yellow", command=lambda: self._cmd("rgb_yellow"), width=7).pack(side="left", padx=2)
        ttk.Label(led, text="  Flu LED:").pack(side="left")
        self.flu_led_var = tk.IntVar(value=0)
        ttk.Scale(led, from_=0, to=255, variable=self.flu_led_var, orient="horizontal", length=100).pack(side="left", padx=2)
        ttk.Button(led, text="1B", command=lambda: self._cmd("flu_led_1b"), width=3).pack(side="left", padx=1)
        self.flu_led_16_var = tk.IntVar(value=0)
        ttk.Scale(led, from_=0, to=65535, variable=self.flu_led_16_var, orient="horizontal", length=100).pack(side="left", padx=2)
        ttk.Button(led, text="2B", command=lambda: self._cmd("flu_led_2b"), width=3).pack(side="left", padx=1)
        ttk.Button(led, text="Off", command=lambda: self._cmd("flu_led_off"), width=5).pack(side="left", padx=2)

        # Misc
        fan = ttk.LabelFrame(self.root, text="Misc", padding=8)
        fan.pack(fill="x", padx=10, pady=3)
        ttk.Button(fan, text="Fan ON", command=lambda: self._cmd("drv_fan_on"), width=11).pack(side="left", padx=2)
        ttk.Button(fan, text="Fan OFF", command=lambda: self._cmd("drv_fan_off"), width=11).pack(side="left", padx=2)
        ttk.Button(fan, text="Beep", command=lambda: self._cmd("beep_on"), width=7).pack(side="left", padx=2)
        ttk.Button(fan, text="Quiet", command=lambda: self._cmd("beep_off"), width=7).pack(side="left", padx=2)

        # Motor direct control
        direct = ttk.LabelFrame(self.root, text="Direct Motor Control", padding=8)
        direct.pack(fill="x", padx=10, pady=3)
        ttk.Label(direct, text="Motor:").pack(side="left")
        self.direct_motor_var = tk.IntVar(value=0)
        motor_spin = ttk.Spinbox(direct, from_=0, to=5, textvariable=self.direct_motor_var, width=3)
        motor_spin.pack(side="left", padx=3)
        ttk.Button(direct, text="Reset", command=lambda: self._cmd("direct_reset"), width=8).pack(side="left", padx=3)
        ttk.Button(direct, text="Stop", command=lambda: self._cmd("direct_stop"), width=8).pack(side="left", padx=3)
        ttk.Button(direct, text="Query", command=lambda: self._cmd("direct_query"), width=8).pack(side="left", padx=3)

        # System
        misc = ttk.LabelFrame(self.root, text="System", padding=8)
        misc.pack(fill="x", padx=10, pady=3)
        ttk.Button(misc, text="Status", command=lambda: self._cmd("status"), width=12).pack(side="left", padx=3)
        ttk.Button(misc, text="ADC Read", command=lambda: self._cmd("adc_read"), width=12).pack(side="left", padx=3)
        ttk.Button(misc, text="All Opto", command=lambda: self._cmd("opto"), width=12).pack(side="left", padx=3)
        ttk.Button(misc, text="Home All", command=lambda: self._cmd("home_all"), width=12).pack(side="left", padx=3)
        ttk.Button(misc, text="Reset All", command=lambda: self._cmd("reset_all"), width=12).pack(side="left", padx=3)
        ttk.Button(misc, text="Stop All", command=lambda: self._cmd("stop_all"), width=12).pack(side="left", padx=3)

        # --- Motor Parameters ---
        params_frame = ttk.LabelFrame(self.root, text="Motor & Device Parameters", padding=8)
        params_frame.pack(fill="x", padx=10, pady=3)

        param_row1 = ttk.Frame(params_frame)
        param_row1.pack(fill="x", pady=2)
        ttk.Label(param_row1, text="Param:").pack(side="left")
        self.param_name_var = tk.StringVar(value="_dp_magnet")
        param_combo = ttk.Combobox(param_row1, textvariable=self.param_name_var, width=18, values=[
            "_mt_cabin_dp", "_mt_y_dp", "_mt_z_dp", "_mt_flu_dp",
            "_mt_padr_dp", "_mt_padl_dp",
            "_dp_chip", "_dp_magnet", "_dp_pushpad", "_dp_model",
            "_dp_flu", "_dp_pmt",
        ])
        param_combo.pack(side="left", padx=3)
        ttk.Button(param_row1, text="Read", command=lambda: self._cmd("param_read"), width=8).pack(side="left", padx=3)
        ttk.Button(param_row1, text="Read All", command=lambda: self._cmd("param_read_all"), width=10).pack(side="left", padx=3)
        ttk.Button(param_row1, text="Write", command=lambda: self._cmd("param_write"), width=8).pack(side="left", padx=3)
        ttk.Button(param_row1, text="Save Flash", command=lambda: self._cmd("param_save"), width=10).pack(side="left", padx=3)

        param_row2 = ttk.Frame(params_frame)
        param_row2.pack(fill="x", pady=2)
        ttk.Label(param_row2, text="Values (comma-sep):").pack(side="left")
        self.param_values_var = tk.StringVar(value="")
        ttk.Entry(param_row2, textvariable=self.param_values_var, width=60).pack(side="left", padx=3, fill="x", expand=True)

        # Log
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=3)
        self.log = tk.Text(log_frame, height=8, font=("Menlo", 10), state="disabled")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _connect_async(self, home=False):
        threading.Thread(target=self._connect, args=(home,), daemon=True).start()

    def _connect(self, home=False):
        self.status_var.set("Connecting...")
        self._log(f"Connecting to {PORT}...")
        try:
            self.uart = DropletBotUart()
            self.uart.init(PORT, 115200)
            time.sleep(2)
            self.proxy = SignalBoardProxy(self.uart)
            self.drv = MotorBoardProxy(self.uart)

            now = datetime.now()
            t = (now.year % 100, now.month, now.day, now.hour, now.minute, now.second)
            self.proxy.login(*t)
            time.sleep(0.3)
            self.drv.login(*t)
            time.sleep(0.3)

            v1 = self.proxy.version()
            v2 = self.drv.version()

            mcu_str = v1.version_string if v1 else "FAIL"
            drv_str = v2.version_string if v2 else "FAIL"

            self.connected = True
            self.status_var.set(f"MCU: {mcu_str}  |  Motor: {drv_str}")
            self._log(f"MCU: {mcu_str}")
            self._log(f"Motor: {drv_str}")

            if home and drv_str != "FAIL":
                self._log("Auto-homing all motors...")
                self.status_var.set("Homing...")
                r = self.drv.cabin_mag_reset()
                self._log(f"  cabin_mag_reset: {r}")
                r = self.drv.pushpad_reset()
                self._log(f"  pushpad_reset: {r}")
                r = self.drv.flu_reset()
                self._log(f"  flu_reset: {r}")
                r = self.drv.pmt_reset()
                self._log(f"  pmt_reset: {r}")
                self.status_var.set(f"MCU: {mcu_str}  |  Motor: {drv_str}  |  Homed")
                self._log("All motors homed.")
        except Exception as e:
            self.status_var.set(f"Error: {e}")
            self._log(f"Error: {e}")

    def _disconnect(self):
        if self.uart:
            self.uart.close()
            self.uart = None
        self.connected = False
        self.status_var.set("Disconnected")
        self._log("Disconnected")

    def _cmd(self, action):
        if not self.connected:
            self._log("Not connected!")
            return
        threading.Thread(target=self._run_cmd, args=(action,), daemon=True).start()

    def _motor_home(self, motor_id, name):
        """Home motor using absolute move to 0 (per Qt debug tool convention)."""
        self._log(f"Homing {name} (motor {motor_id})...")
        r = self.drv.motor_control(motor_id, MT_HOME, 0)
        self._log(f"  Result: {r}")

    def _run_cmd(self, action):
        try:
            # --- Chip Tray (0=in, 1=out) ---
            if action == "tray_home":
                self._log("Homing tray + magnet (cabin_mag_reset)...")
                r = self.drv.cabin_mag_reset()
                self._log(f"  Result: {r}")
            elif action == "tray_out":
                self._log("Tray OUT...")
                r = self.drv.chip_cabin_ctrl(1)
                self._log(f"  Result: {r}")
            elif action == "tray_in":
                self._log("Tray IN...")
                r = self.drv.chip_cabin_ctrl(0)
                self._log(f"  Result: {r}")
            elif action == "tray_read":
                r = self.drv.chip_cabin_read()
                self._log(f"Tray: {r}")

            # --- Pogo Pins (0=press, 1=release) ---
            elif action == "pogo_home":
                self._log("Homing pogos (pushpad_reset)...")
                r = self.drv.pushpad_reset()
                self._log(f"  Result: {r}")
            elif action == "pogo_home_l":
                self._motor_home(MT_POGO_R, "pogo left (mt4)")
            elif action == "pogo_home_r":
                self._motor_home(MT_POGO_L, "pogo right (mt5)")
            elif action == "pogo_press":
                self._log("Pressing pogos...")
                r = self.drv.pushpad_ctrl(1)
                self._log(f"  Press: {r}")
            elif action == "pogo_release":
                self._log("Releasing pogos...")
                r = self.drv.pushpad_ctrl(0)
                self._log(f"  Release: {r}")
            elif action == "pogo_read":
                r = self.drv.pushpad_read()
                self._log(f"Pogo: {r}")

            # --- Magnet (0=disengage, 1=engage) ---
            elif action == "mag_home":
                self._log("Homing magnet only (motor 2)...")
                r = self.drv.motor_control(MT_MAG_Z, MT_HOME, 0)
                self._log(f"  Result: {r}")
            elif action == "mag_engage":
                self._log("Magnet engage (1=MAG_STATE_ENGAGED)...")
                r = self.drv.mag_ctrl(1)
                self._log(f"  Engage: {r}")
            elif action == "mag_disengage":
                self._log("Magnet disengage (0=MAG_STATE_DISENGAGED)...")
                r = self.drv.mag_ctrl(0)
                self._log(f"  Disengage: {r}")
            elif action == "mag_read":
                r = self.drv.mag_read()
                self._log(f"Magnet: {r}")

            # --- Fluorescence Filter ---
            elif action == "flu_home":
                self._log("Homing fluorescence (flu_reset)...")
                r = self.drv.flu_reset()
                self._log(f"  Result: {r}")
            elif action == "flu_read":
                r = self.drv.fluorescence_read()
                self._log(f"Fluorescence: {r}")
            elif action in ("flu_1", "flu_2", "flu_3", "flu_4", "flu_5"):
                pos = int(action.split("_")[1])
                self._log(f"Fluorescence -> pos {pos}...")
                r = self.drv.fluorescence_ctrl(pos)
                self._log(f"  Result: {r}")

            # --- PMT Motor ---
            elif action == "pmt_home":
                self._log("Homing PMT (pmt_reset)...")
                r = self.drv.pmt_reset()
                self._log(f"  Result: {r}")
            elif action == "pmt_read":
                r = self.drv.pmt_read()
                self._log(f"PMT: {r}")
            elif action.startswith("pmt_"):
                pos = int(action.split("_")[1])
                self._log(f"PMT -> pos {pos}...")
                r = self.drv.pmt_ctrl(pos)
                self._log(f"  Result: {r}")

            # --- LEDs ---
            elif action == "rgb_off":
                r = self.proxy.rgb_light_ctrl(0)
                self._log(f"RGB off: {r}")
            elif action == "rgb_red":
                r = self.proxy.rgb_light_ctrl(1)
                self._log(f"RGB red: {r}")
            elif action == "rgb_green":
                r = self.proxy.rgb_light_ctrl(2)
                self._log(f"RGB green: {r}")
            elif action == "rgb_yellow":
                r = self.proxy.rgb_light_ctrl(3)
                self._log(f"RGB yellow: {r}")
            elif action == "flu_led_1b":
                val = min(self.flu_led_var.get(), 255)
                self._log(f"Flu LED 1-byte -> {val}/255...")
                packet = self.proxy._transport._make_cmd_packet(0x1223, bytes([val]))
                self.proxy._transport._wr(packet, 0x1223)
                self._log(f"  Sent")
            elif action == "flu_led_2b":
                val = self.flu_led_16_var.get()
                self._log(f"Flu LED 16-bit -> {val}/65535 ({val*100/65535:.1f}%)...")
                r = self.proxy.fluorescence_ctrl(val)
                self._log(f"  Result: {r}")
            elif action == "flu_led_off":
                self.flu_led_var.set(0)
                packet = self.proxy._transport._make_cmd_packet(0x1223, bytes([0]))
                self.proxy._transport._wr(packet, 0x1223)
                self._log(f"Flu LED off")

            # --- Fans ---
            elif action == "drv_fan_on":
                r = self.drv.fan_ctrl(1)
                self._log(f"Motor fan ON: {r}")
            elif action == "drv_fan_off":
                r = self.drv.fan_ctrl(0)
                self._log(f"Motor fan OFF: {r}")
            elif action == "beep_on":
                r = self.proxy.buzzer_ctrl(1)
                self._log(f"Buzzer ON: {r}")
            elif action == "beep_off":
                r = self.proxy.buzzer_ctrl(0)
                self._log(f"Buzzer OFF: {r}")

            # --- System ---
            elif action == "status":
                s = self.drv.status()
                if s:
                    self._log(f"Motor: cabin={s.cabin}, mag={s.mag}, flu={s.flu}, "
                              f"lpush={s.lpush}, rpush={s.rpush}, pmt={s.pmt}")
                else:
                    self._log("Motor status: FAIL")
            elif action == "adc_read":
                r = self.proxy.read_adc_data()
                if r:
                    self._log(f"ADC: ch0={r.ch0:.2f}V ch1={r.ch1:.2f}V ch2={r.ch2:.2f}V ch3={r.ch3:.2f}V "
                              f"ch4={r.ch4:.2f}V ch5={r.ch5:.2f}V ch6={r.ch6:.2f}V ch7={r.ch7:.2f}V")
                else:
                    self._log("ADC read: FAIL")
            elif action == "opto":
                r = self.drv.motor_opto_query()
                self._log(f"Opto sensors: {r}")
            elif action == "home_all":
                self._log("Homing all (high-level resets)...")
                r = self.drv.cabin_mag_reset()
                self._log(f"  cabin_mag_reset: {r}")
                r = self.drv.pushpad_reset()
                self._log(f"  pushpad_reset: {r}")
                r = self.drv.flu_reset()
                self._log(f"  flu_reset: {r}")
                r = self.drv.pmt_reset()
                self._log(f"  pmt_reset: {r}")
                self._log("All homed.")
            elif action == "reset_all":
                self._log("Resetting all motors (action=4)...")
                for mid, name in [(MT_CABIN, "tray"), (MT_PMT, "PMT"),
                                  (MT_MAG_Z, "magnet"), (MT_FLU, "fluorescence"),
                                  (MT_POGO_R, "pogo L(mt4)"), (MT_POGO_L, "pogo R(mt5)")]:
                    self._log(f"  Resetting {name} (motor {mid})...")
                    r = self.drv.motor_control(mid, MT_HOME, 0)
                    self._log(f"    Result: {r}")
                self._log("All reset commands sent.")
            elif action == "stop_all":
                self._log("Stopping all motors...")
                for mid, name in [(MT_CABIN, "tray"), (MT_PMT, "PMT"),
                                  (MT_MAG_Z, "magnet"), (MT_FLU, "fluorescence"),
                                  (MT_POGO_R, "pogo L(mt4)"), (MT_POGO_L, "pogo R(mt5)")]:
                    r = self.drv.motor_control(mid, MT_STOP, 0)
                    self._log(f"  Stop {name}: {r}")
                self._log("All motors stopped.")

            # --- Direct Motor Control ---
            elif action == "direct_reset":
                mid = self.direct_motor_var.get()
                self._log(f"Reset motor {mid} (action=4)...")
                r = self.drv.motor_control(mid, MT_HOME, 0)
                self._log(f"  Result: {r}")
            elif action == "direct_stop":
                mid = self.direct_motor_var.get()
                self._log(f"Stop motor {mid}...")
                r = self.drv.motor_control(mid, MT_STOP, 0)
                self._log(f"  Result: {r}")
            elif action == "direct_query":
                mid = self.direct_motor_var.get()
                self._log(f"Query motor {mid}...")
                r = self.drv.motor_position_query(mid)
                self._log(f"  Position: {r}")

            # --- Parameters ---
            elif action == "param_read":
                name = self.param_name_var.get()
                self._read_param(name)
            elif action == "param_read_all":
                for name in ["_mt_cabin_dp", "_mt_y_dp", "_mt_z_dp", "_mt_flu_dp",
                              "_mt_padr_dp", "_mt_padl_dp",
                              "_dp_chip", "_dp_magnet", "_dp_pushpad", "_dp_model",
                              "_dp_flu", "_dp_pmt"]:
                    self._read_param(name)
            elif action == "param_write":
                self._write_param()
            elif action == "param_save":
                name = self.param_name_var.get()
                self._log(f"Saving {name} to flash...")
                pkt = self.drv._transport._make_cmd_packet(0x1162, name.encode('utf-8') + b'\x00')
                r = self.drv._transport._wr(pkt, 0x1162, timeout_s=5.0)
                self._log(f"  Save: {'OK' if r is not None else 'FAIL'}")

        except Exception as e:
            self._log(f"Error: {e}")

    # ------------------------------------------------------------------ Param helpers
    _MOTOR_FIELDS = [
        ("neg_lim", "f"), ("pos_lim", "f"), ("lead", "f"),
        ("origin_offset", "f"), ("origin_area", "f"), ("step_len", "f"),
        ("polarity", "i"), ("I_hold", "i"), ("I_run", "i"), ("subdiv", "i"),
        ("run_sgt", "i"), ("rst_sgt", "i"), ("rst_speed", "i"), ("run_speed", "i"),
    ]

    _DEVICE_FIELDS = {
        "_dp_chip":    [("out_pos", "i"), ("mag_pos", "i"), ("in_pos", "i")],
        "_dp_magnet":  [("engaged_pos", "i"), ("disengaged_pos", "i"), ("y_0", "i"), ("y_space", "i")],
        "_dp_pushpad": [("pos", "i")],
        "_dp_model":   [("model_id", "i"), ("use_pmt", "I"), ("mag_z_home_dir", "I"), ("config", "I")],
        "_dp_flu":     [(f"pos{i+1}", "i") for i in range(5)],
        "_dp_pmt":     [(f"pos{i+1}", "i") for i in range(5)],
    }

    def _get_fields(self, name: str):
        if name.startswith("_mt_"):
            return self._MOTOR_FIELDS
        return self._DEVICE_FIELDS.get(name, [])

    def _read_param(self, name: str):
        r = self.drv.get_params(name)
        if not r or not hasattr(r, 'value') or len(r.value) == 0:
            self._log(f"{name}: READ FAILED")
            return

        fields = self._get_fields(name)
        if not fields:
            self._log(f"{name}: {r.value.hex()}")
            return

        fmt = ">" + "".join(f for _, f in fields)
        expected = struct.calcsize(fmt)
        data = r.value[:expected]
        if len(data) < expected:
            self._log(f"{name}: short data ({len(data)}/{expected} bytes)")
            return

        values = struct.unpack(fmt, data)
        parts = []
        for (fname, _), val in zip(fields, values):
            if isinstance(val, float):
                parts.append(f"{fname}={val:.4f}")
            else:
                parts.append(f"{fname}={val}")
        self._log(f"{name}: {', '.join(parts)}")

        # Pre-fill the values entry for editing
        val_strs = []
        for (_, f), val in zip(fields, values):
            if f == "f":
                val_strs.append(f"{val:.6f}")
            else:
                val_strs.append(str(val))
        if name == self.param_name_var.get():
            self.param_values_var.set(", ".join(val_strs))

    def _write_param(self):
        name = self.param_name_var.get()
        fields = self._get_fields(name)
        if not fields:
            self._log(f"Unknown param: {name}")
            return

        val_text = self.param_values_var.get()
        try:
            raw_vals = [v.strip() for v in val_text.split(",")]
            if len(raw_vals) != len(fields):
                self._log(f"Expected {len(fields)} values, got {len(raw_vals)}")
                return

            packed = b""
            for (fname, fmt), raw in zip(fields, raw_vals):
                if fmt == "f":
                    packed += struct.pack(">f", float(raw))
                elif fmt == "I":
                    packed += struct.pack(">I", int(raw))
                else:
                    packed += struct.pack(">i", int(raw))

            self._log(f"Writing {name}: {len(packed)} bytes...")
            ok = self.drv.set_params(name, packed)
            self._log(f"  Write: {'OK' if ok else 'FAIL'}")
            self._log(f"  Use 'Save Flash' to persist across reboots")
        except (ValueError, struct.error) as e:
            self._log(f"Parse error: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MotorTestUI(root)
    root.mainloop()
