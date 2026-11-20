# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Board alarms in the status pane: a raised code joins the active alarms,
while a clear (active 0) retires it instead of logging a new alarm. Plus the
firmware and STATUS display formatting. Hardware-free, no Redis."""

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import AlarmRaised, FirmwareVersionsUpdated
from portable_dropbot_status_and_controls.message_handlers import (
    message_handler as mod,
)
from portable_dropbot_status_and_controls.models.model import (
    PortableDropbotStatusAndControlsModel,
)


@pytest.fixture
def handler(request):
    h = mod.PortableDropbotStatusAndControlsMessageHandler(
        model=PortableDropbotStatusAndControlsModel(), name=f"test_{request.node.name}"
    )
    yield h
    h.teardown()


def _frame(code, active):
    """One REPORT_ALARM frame as the backend publishes it."""
    text = f"[{code}] Temperature sensor fault"

    return AlarmRaised(
        command="4722",
        alarms=[text],
        reports=[
            {
                "text": text,
                "code": code,
                "title": "Temperature sensor fault",
                "active": active,
                "level": 2,
            }
        ],
    ).model_dump_json()


def test_a_raise_adds_the_code_and_logs_it(handler):
    handler._on_alarm_triggered(_frame("05003", 1))

    assert list(handler.model.active_alarms) == ["05003"]
    assert "[05003]" in handler.model.last_alarm
    assert handler.model.alarm_log.count("[05003]") == 1


def test_a_clear_retires_the_code_instead_of_raising_it_again(handler):
    handler._on_alarm_triggered(_frame("05003", 1))
    raised = handler.model.last_alarm

    handler._on_alarm_triggered(_frame("05003", 0))

    assert handler.model.active_alarms == {}
    assert handler.model.active_alarms_display == "None"
    assert handler.model.last_alarm == raised
    assert (
        handler.model.alarm_log.splitlines()[0]
        .split(" ", 1)[1]
        .startswith("Cleared: [05003]")
    )


def test_legacy_payload_without_reports_still_logs(handler):
    handler._on_alarm_triggered('{"command": "4722", "alarms": ["[01006] HV off"]}')

    assert handler.model.last_alarm == "[01006] HV off"
    assert handler.model.active_alarms == {}


def test_firmware_versions_show_in_board_status(handler):
    handler._on_firmware_versions_updated_triggered(
        FirmwareVersionsUpdated(
            mcu="DroSIG_1.0.1.32", motor="DroDri_1.0.0.27"
        ).model_dump_json()
    )

    assert (
        handler.model.firmware_display == "MCU DroSIG_1.0.1.32, Motor DroDri_1.0.0.27"
    )
    assert handler.model.alarm_log == "-"


@pytest.mark.parametrize(
    ("value", "expected"), [(655.35, "n/a"), (31.5, "31.50 °C"), (0.0, "0.00 °C")]
)
def test_dead_humidity_sensor_reads_n_a(value, expected):
    assert mod.format_environment_reading(value, "°C") == expected


@pytest.mark.parametrize(
    ("fan_duty", "expected"),
    [(0, "Off"), (1, "Fan 1 on"), (2, "Fan 2 on"), (3, "Fan 1, Fan 2 on")],
)
def test_fan_duty_is_a_bitmask(fan_duty, expected):
    assert mod.summarize_fan_duty(fan_duty) == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, ("n/a", "n/a")),
        ({"hv_setpoint": 0.0, "faults": []}, ("not set", "none")),
        (
            {"hv_setpoint": 120.0, "faults": ["output-current-exceeded"]},
            ("120.00 V", "output-current-exceeded"),
        ),
    ],
)
def test_status_tail_reads_like_the_vendor_ui(data, expected):
    assert mod.summarize_status_tail(data) == expected


def test_status_update_drops_the_dead_pmt_key_and_shows_the_halt(handler):
    handler._on_status_updated_triggered('{"halted": true, "fan_duty": 1}')

    assert handler.model.halted is True
    assert handler.model.fan_duty_display == "Fan 1 on"
    assert not hasattr(handler.model, "pmt_display")
