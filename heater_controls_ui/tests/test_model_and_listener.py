"""Hardware-free tests for the heater controls UI logic.

Covers the pure helpers that turn backend signals into model state: the heater
dropdown selection rules and the telemetry-to-readout formatting.
"""
import pytest

from heater_controls_ui.listener import resolve_selection, format_telemetry


# --- dropdown selection -----------------------------------------------------

def test_resolve_selection_defaults_to_first_when_unset():
    assert resolve_selection("", ["tec1", "tec2"]) == {"selected_heater": "tec1"}


def test_resolve_selection_repairs_stale_selection():
    assert resolve_selection("gone", ["tec1", "tec2"]) == {"selected_heater": "tec1"}


def test_resolve_selection_keeps_valid_selection():
    assert resolve_selection("tec2", ["tec1", "tec2"]) == {}


def test_resolve_selection_empty_list_no_change():
    assert resolve_selection("tec1", []) == {}


# --- telemetry formatting ---------------------------------------------------

def test_format_telemetry_pid_frame():
    data = {
        "_frame": "PID_TEC1",
        "pid_temperature": 41.234,
        "pwm_percentage": 30,
        "temperatures": {"top": 41.2, "bottom": 40.9},
    }
    out = format_telemetry(data)
    assert out["pid_temp_text"] == "PID temp: 41.23 °C"
    assert out["pwm_text"] == "PWM: 30%"
    assert out["temps_text"] == "Temps: top=41.2, bottom=40.9"


def test_format_telemetry_open_loop_uses_pwm_tec1():
    out = format_telemetry({"_frame": "TEMP", "pwm_tec1": 12})
    assert out["pwm_text"] == "PWM: 12%"


def test_format_telemetry_ignores_invalid_temp_sentinel():
    out = format_telemetry({"_frame": "PID_TEC1", "pid_temperature": -50})
    assert "pid_temp_text" not in out


def test_format_telemetry_whoami():
    out = format_telemetry({"_frame": "WHOAMI", "device_id": "heater-7", "uid": "abc"})
    assert out == {"board_id_text": "Board: heater-7"}


def test_format_telemetry_whoami_falls_back_to_uid():
    out = format_telemetry({"_frame": "WHOAMI", "uid": "abcd1234"})
    assert out == {"board_id_text": "Board: abcd1234"}


def test_format_telemetry_err_frame():
    out = format_telemetry({"_frame": "ERR", "heater": "tec1", "message": "overtemp"})
    assert out == {"status_text": "Error (tec1): overtemp"}


def test_format_telemetry_info_frame_no_updates():
    assert format_telemetry({"_frame": "INFO", "event": "pid_started"}) == {}
