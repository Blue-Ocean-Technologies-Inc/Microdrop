# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The driver's on_alarm hands one AlarmReport per frame; the backend
carries its fields (code, title, active, level) through on ALARM_RAISED so
the status pane can tell a clear from a raise. Hardware-free, no Redis."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
from dropbot_portable.commands import AlarmReport

# Microdrop package imports.
from portable_dropbot_controller import portable_dropbot_controller_base as base
from portable_dropbot_controller.consts import AlarmRaised


def _publish(monkeypatch, alarms):
    published = []
    monkeypatch.setattr(
        base, "alarm_raised_publisher", SimpleNamespace(publish=published.append)
    )

    base.PortableDropbotControllerBase._publish_alarm(None, 0x1272, alarms)

    return AlarmRaised.model_validate(published[0])


def test_alarm_report_fields_ride_along(monkeypatch):
    report = AlarmReport.from_fields("05003", "sensor 3 back", active=0, level=2)

    alarm = _publish(monkeypatch, [report])

    entry = alarm.reports[0]
    assert (entry.code, entry.active, entry.level) == ("05003", 0, 2)
    assert entry.title == report.title
    assert entry.detail == "sensor 3 back"
    assert alarm.alarms == [str(report)]
    assert alarm.command == str(0x1272)


def test_a_plain_string_from_an_older_driver_travels_as_text(monkeypatch):
    alarm = _publish(monkeypatch, ["[01006] HV off its setpoint"])

    entry = alarm.reports[0]
    assert entry.text == "[01006] HV off its setpoint"
    assert entry.code is None
    assert entry.active is None
