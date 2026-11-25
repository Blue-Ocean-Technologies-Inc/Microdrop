# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications demo's real log records: log files parsed as the app's
handler would have seen them, the scrubber removing machine- and
person-specific text, and the stored samples free of it."""

# Standard library imports.
import inspect
import logging
import re

# Third-party imports.
import pytest

# Microdrop package imports.
from examples.demos.notifications_pane import sample_log_records
from examples.demos.notifications_pane.log_records import log_record, parse_log_text
from examples.demos.notifications_pane.log_scrubber import scrub_log_text

HOME = r"C:\Users\jdoe"
CHECKOUT = rf"{HOME}\PycharmProjects\pixi-microdrop\microdrop-py"

LOG = "\n".join(
    [
        "2026-08-05 16:09:10.123 [INFO:device_viewer.x]: started "
        f'File "{CHECKOUT}\\src\\device_viewer\\x.py", line 3',
        "2026-08-05 16:09:11.500 [WARNING:device_viewer.models.perspective]: Need 4 "
        f'points File "{CHECKOUT}\\src\\device_viewer\\models\\p.py", line 78',
        "2026-08-05 16:09:12.000 [ERROR:traits]: Exception occurred in handler "
        f'File "{CHECKOUT}\\.pixi\\envs\\default\\Lib\\site-packages\\traits\\x.py", '
        "line 45",
        "Traceback (most recent call last):",
        f'  File "{CHECKOUT}\\src\\heater_controls_ui\\plots\\log_view.py", line 175',
        "TypeError: bad",
    ]
)


def test_a_log_parses_to_its_warning_and_error_records():
    records = parse_log_text(LOG)

    assert [record.levelno for record in records] == [logging.WARNING, logging.ERROR]
    assert records[0].message == "Need 4 points"
    assert records[1].message == "Exception occurred in handler"
    assert records[1].traceback.splitlines()[-1] == "TypeError: bad"
    assert records[0].created % 1 == pytest.approx(0.5)


def test_a_record_carries_its_traceback_as_exception_text():
    record = log_record(parse_log_text(LOG)[1], created=100.0)

    assert record.getMessage() == "Exception occurred in handler"
    assert record.exc_text.startswith("Traceback")
    assert record.created == 100.0


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            f'File "{CHECKOUT}\\src\\device_viewer\\models\\x.py", line 3',
            'File "src/device_viewer/models/x.py", line 3',
        ),
        (
            f"{CHECKOUT}\\.pixi\\envs\\default\\Lib\\site-packages\\traits\\a.py",
            "<env>/Lib/site-packages/traits/a.py",
        ),
        (
            f"Plotted experiment {HOME}\\Documents\\Sci-Bots\\Microdrop\\Experiments"
            "\\2026_11_18-16_48_08 is missing",
            "Plotted experiment <experiment> is missing",
        ),
        (rf"saved to {HOME}\Desktop\run.csv", "saved to <home>/Desktop/run.csv"),
        ("/home/pi/.config/x.json", "<home>/.config/x.json"),
        ("ti...6_08_05-16_01_58_191000)", "ti...<timestamp>)"),
        ("ssh portable-dropbot-user@dropbot failed", "ssh <user@host> failed"),
        ("mail jane.doe@example.com", "mail <user@host>"),
        ("connect 192.168.1.42:6379", "connect <ip>:6379"),
        ("user AzureAD\\JaneDoe", "user <user>"),
        (
            "hwid USB VID:PID=16C0:0483 SER=1234567 LOCATION=1-1",
            "hwid USB VID:PID=16C0:0483 LOCATION=1-1",
        ),
        (r"USB\VID_16C0&PID_0483\5A3B9C11", r"USB\VID_16C0&PID_0483"),
        ("board serial number: AB12CD34EF", "board serial number: <serial>"),
        ("No device for hwids ['VID:PID=16C0:0483'] found", None),
    ],
)
def test_the_scrubber_neutralises_private_text(text, expected):
    assert scrub_log_text(text) == (text if expected is None else expected)


def test_the_stored_samples_hold_nothing_private():
    source = inspect.getsource(sample_log_records)
    private = [
        r"Users\\",
        r"Info\\",
        "AzureAD",
        "@",
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        r"SER=",
        r"\d{4}_\d{2}_\d{2}-\d{2}",
        r"Experiments[\\/]",
    ]

    for pattern in private:
        assert not re.search(pattern, source), pattern
