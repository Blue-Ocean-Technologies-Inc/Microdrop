# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Log records reach the notifications in batches: collapsed by key, from
any thread, without the ignored or the plugin's own records, and without a
failure on the way ever logging back into the handler."""

# Standard library imports.
import logging
import sys
import threading

# Third-party imports.
import pytest

# Microdrop package imports.
from notifications.consts import (
    LOG_DELIVERY_CHUNK,
    LOG_RECORDED_EXTRA,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from notifications.models.notification_center import NotificationCenter
from notifications.services.log_forwarder import NotificationLogHandler

#: A logger only these tests write to; nothing reaches the root logger.
TEST_LOGGER_NAME = "notifications_tests.source"


class FakeTimer:
    """Collects the deliveries a handler schedules, to run them by hand."""

    def __init__(self):
        self.scheduled = []

    def __call__(self, milliseconds, callable):
        self.scheduled.append(callable)

    def run_all(self):
        scheduled, self.scheduled = self.scheduled, []

        for callable in scheduled:
            callable()


@pytest.fixture
def forwarding():
    """A center, a handler on a private logger, and the handler's timer."""
    center = NotificationCenter()
    timer = FakeTimer()
    handler = NotificationLogHandler(
        center,
        ignore_rules=[(TEST_LOGGER_NAME, r"routine")],
        invoke_after=timer,
        buffer_limit=100,
    )
    source = logging.getLogger(TEST_LOGGER_NAME)
    source.propagate = False
    source.addHandler(handler)

    yield center, source, timer

    source.removeHandler(handler)


def test_a_burst_of_repeats_is_one_entry_and_one_delivery(forwarding):
    center, source, timer = forwarding

    for _ in range(5000):
        source.warning("Pump pressure low")

    assert len(timer.scheduled) == 1
    assert center.entries == []

    timer.run_all()

    assert len(center.entries) == 1

    entry = center.entries[0]

    # The buffer holds the newest 100; the rest were dropped as a flood.
    assert entry.count == 100
    assert entry.severity == SEVERITY_WARNING
    assert (entry.category, entry.source) == ("log", TEST_LOGGER_NAME)


def test_records_from_other_threads_arrive_on_delivery(forwarding):
    center, source, timer = forwarding
    threads = [
        threading.Thread(target=source.error, args=(f"Worker {number} failed",))
        for number in range(4)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    timer.run_all()

    assert sorted(entry.title for entry in center.entries) == [
        f"Worker {number} failed" for number in range(4)
    ]
    assert {entry.severity for entry in center.entries} == {SEVERITY_ERROR}


def test_a_record_after_a_delivery_schedules_the_next(forwarding):
    center, source, timer = forwarding

    source.warning("one")
    timer.run_all()
    source.warning("one")
    timer.run_all()

    assert center.entries[0].count == 2


def test_ignored_and_own_records_are_not_forwarded(forwarding):
    center, source, timer = forwarding
    own = logging.getLogger("notifications.controllers.notifications_controller")
    own_handler = source.handlers[0]
    own.addHandler(own_handler)

    try:
        source.warning("routine start-up line")
        own.error("Could not open a path")

    finally:
        own.removeHandler(own_handler)

    assert timer.scheduled == []


def test_a_record_already_listed_by_its_dialog_is_not_forwarded(forwarding):
    center, source, timer = forwarding

    source.error("DropBot halted", extra=LOG_RECORDED_EXTRA)

    assert timer.scheduled == []


def test_an_exception_shows_its_traceback_and_keys_on_its_last_line(forwarding):
    center, source, timer = forwarding

    for error in (
        ValueError("bad value"),
        KeyError("missing"),
        ValueError("bad value"),
    ):
        try:
            raise error

        except Exception:
            source.exception("Handler failed")

    timer.run_all()

    assert [entry.count for entry in center.entries] == [2, 1]

    entry = center.entries[0]

    assert entry.title == "Handler failed"
    assert "ValueError: bad value" in entry.detail
    assert entry.monospace_detail


def log_traits_handler_failure(source, error):
    """Log ``error`` on the traits logger as Traits does, with the exception."""

    try:
        raise error

    except Exception:
        record = source.makeRecord(
            "traits",
            logging.ERROR,
            __file__,
            1,
            "Exception occurred in traits notification handler for event object",
            None,
            sys.exc_info(),
        )

    source.handle(record)


def test_a_traits_handler_failure_is_titled_by_its_exception(forwarding):
    center, source, timer = forwarding

    log_traits_handler_failure(source, TypeError("unsupported operand"))
    timer.run_all()

    entry = center.entries[0]

    assert entry.title == "TypeError: unsupported operand"
    assert entry.detail.startswith("Exception occurred in traits notification")
    assert entry.monospace_detail


def test_a_multi_line_exception_is_titled_by_its_first_line(forwarding):
    center, source, timer = forwarding
    error = ValueError(
        "1 validation error for StepModel\n"
        "voltage\n"
        "  Input should be a valid integer\n"
        "    For further information visit https://errors.pydantic.dev/2/v/int"
    )

    log_traits_handler_failure(source, error)
    timer.run_all()

    assert center.entries[0].title == "ValueError: 1 validation error for StepModel"


def test_an_exception_note_does_not_become_the_title(forwarding):
    center, source, timer = forwarding
    error = TypeError("unsupported operand")
    error.add_note("while applying the step")

    log_traits_handler_failure(source, error)
    timer.run_all()

    entry = center.entries[0]

    assert entry.title == "TypeError: unsupported operand"
    assert "while applying the step" in entry.detail


def test_colour_codes_from_the_console_formatter_are_stripped(forwarding):
    center, source, timer = forwarding
    record = source.makeRecord(
        "\x1b[36mcoloured.logger\x1b[0m",
        logging.WARNING,
        __file__,
        1,
        "\x1b[1mBold\x1b[0m text",
        None,
        None,
    )

    source.handle(record)
    timer.run_all()

    assert (center.entries[0].source, center.entries[0].title) == (
        "coloured.logger",
        "Bold text",
    )


def test_a_failing_delivery_is_reported_to_stderr_not_logged(forwarding, capsys):
    center, source, timer = forwarding

    def failing_post(**arguments):
        raise RuntimeError("model broken")

    center.post = failing_post
    source.warning("anything")
    timer.run_all()

    assert "model broken" in capsys.readouterr().err
    assert timer.scheduled == []


def test_records_below_the_handler_level_are_not_forwarded(forwarding):
    center, source, timer = forwarding
    source.setLevel(logging.DEBUG)

    try:
        source.info("just information")

    finally:
        source.setLevel(logging.NOTSET)

    assert timer.scheduled == []


def test_a_burst_of_distinct_records_is_posted_a_chunk_per_turn(forwarding):
    center, source, timer = forwarding

    for number in range(LOG_DELIVERY_CHUNK * 2 + 10):
        source.warning(f"record {number}")

    timer.run_all()

    assert len(center.entries) == LOG_DELIVERY_CHUNK
    assert center.entries[0].title == f"record {LOG_DELIVERY_CHUNK - 1}"

    timer.run_all()
    timer.run_all()

    assert len(center.entries) == LOG_DELIVERY_CHUNK * 2 + 10
    assert center.entries[0].title == f"record {LOG_DELIVERY_CHUNK * 2 + 9}"
    assert timer.scheduled == []
