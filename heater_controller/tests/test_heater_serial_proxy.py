"""Hardware-free tests for HeaterSerialProxy telemetry parsing.

The reader thread routes plain-text lines vs. ``§<FRAME>{json}`` telemetry; this
exercises the pure parsing helper that decision relies on (no serial port needed).
"""
from heater_controller.heater_serial_proxy import HeaterSerialProxy


def test_parse_telemetry_line_tags_frame_and_payload():
    frame, pkt = HeaterSerialProxy.parse_telemetry_line('§PID_TEC1{"temp": 41.2, "pwm": 30}')
    assert frame == "PID_TEC1"
    assert pkt == {"temp": 41.2, "pwm": 30, "_frame": "PID_TEC1"}


def test_parse_telemetry_line_without_frame_tag():
    frame, pkt = HeaterSerialProxy.parse_telemetry_line('§{"temp": 25.0}')
    assert frame == ""
    assert pkt == {"temp": 25.0, "_frame": ""}


def test_parse_telemetry_line_no_json_returns_none():
    frame, pkt = HeaterSerialProxy.parse_telemetry_line('§WHOAMI')
    assert frame == "WHOAMI"
    assert pkt is None


def test_parse_telemetry_line_bad_json_returns_none():
    frame, pkt = HeaterSerialProxy.parse_telemetry_line('§INFO{not valid json}')
    assert frame == "INFO"
    assert pkt is None
