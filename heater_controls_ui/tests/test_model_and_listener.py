"""Hardware-free tests for the heater controls UI logic.

Covers the pure helpers that turn backend signals into model state: the heater
dropdown selection rules and the telemetry-to-readout formatting.
"""
import pytest

from heater_controls_ui.telemetry import resolve_selection, format_telemetry


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

def test_format_telemetry_pid_frame_temp_mode():
    # PID_<HEATER> frame in Temp mode drives both temperature and the main PWM.
    data = {
        "_frame": "PID_HEATER1",
        "pid_temperature": 41.234,
        "pwm_percentage": 30,
    }
    out = format_telemetry(data, pid_mode=True)
    assert out["temperature_display"] == "41.2 °C"
    assert out["pwm_display"] == "30 %"


def test_format_telemetry_temp_frame_only_drives_all_temps():
    # A TEMP frame carries only the per-sensor dict; it must not touch the main
    # temperature or PWM readouts.
    out = format_telemetry(
        {"_frame": "TEMP", "temperatures": {"B1": 27.77, "C1": 27.73}}, pid_mode=False
    )
    assert out == {"all_temps_display": "B1: 27.8 °C, C1: 27.7 °C"}


def test_format_telemetry_pwm_mode_ignores_pid_loop_duty():
    # In PWM mode the PID loop's pwm_percentage is 0 (PID disabled); the main PWM
    # readout is echoed from the commanded value by the controller, not telemetry.
    out = format_telemetry(
        {"_frame": "PID_HEATER1", "pid_temperature": 33.0, "pwm_percentage": 0.0},
        pid_mode=False,
    )
    assert "pwm_display" not in out
    assert out["temperature_display"] == "33.0 °C"


def test_format_telemetry_closed_loop_uses_pwm_percentage():
    out = format_telemetry(
        {"_frame": "PID_HEATER1", "pwm_percentage": 64.7}, pid_mode=True
    )
    assert out["pwm_display"] == "64.7 %"


def test_format_telemetry_invalid_temp_sentinel_resets_display():
    out = format_telemetry({"_frame": "PID_HEATER1", "pid_temperature": -50})
    assert out["temperature_display"] == "-"


def test_format_telemetry_whoami():
    out = format_telemetry({"_frame": "WHOAMI", "device_id": "heater-7", "uid": "abc"})
    assert out == {"board_id_text": "heater-7"}


def test_format_telemetry_whoami_falls_back_to_uid():
    out = format_telemetry({"_frame": "WHOAMI", "uid": "abcd1234"})
    assert out == {"board_id_text": "abcd1234"}


def test_format_telemetry_err_and_info_frames_have_no_display_updates():
    assert format_telemetry({"_frame": "ERR", "heater": "tec1", "message": "overtemp"}) == {}
    assert format_telemetry({"_frame": "INFO", "event": "pid_started"}) == {}
