# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The deferred sidebar sections build in order, one per event-loop turn and
each once; what waits on a section runs when it is built, or fails over when
its build raises, without stopping the others (#1064). No Qt: the event loop
is a queue the tests drain."""

# Standard library imports.
from unittest.mock import patch

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.controllers.sidebar_section_builder import SidebarSectionBuilder
from device_viewer.interfaces.descriptors import SidebarSection
from device_viewer.models.deferred_sidebar_section import (
    SECTION_BUILT,
    SECTION_FAILED,
    SECTION_LOADING,
    DeferredSidebarSection,
)

#: The deferred sections log their failed builds and callbacks here.
CONTENT_LOGGER = "microdrop_utils.deferred_content.logger"


class EventLoop:
    """``GUI.invoke_later`` as a queue: one call per turn."""

    def __init__(self):
        self.queue = []

    def invoke_later(self, function, *args):
        self.queue.append((function, args))

    def turn(self):
        function, args = self.queue.pop(0)
        function(*args)

    def drain(self):
        turns = 0

        while self.queue:
            self.turn()
            turns += 1

        return turns


@pytest.fixture
def loop():
    return EventLoop()


@pytest.fixture
def built():
    """Titles of the sections built, in build order."""
    return []


def _deferred(title, built, error=None):
    def build():
        if error is not None:
            raise error

        built.append(title)

        return SidebarSection(title=title)

    return DeferredSidebarSection(title=title, build=build)


def _builder(loop, *sections):
    return SidebarSectionBuilder(
        sections=list(sections), invoke_later=loop.invoke_later
    )


def test_sections_build_in_order_one_per_turn(loop, built):
    builder = _builder(loop, _deferred("A", built), _deferred("B", built))

    builder.start()

    assert built == []

    loop.turn()

    assert built == ["A"]

    loop.turn()

    assert built == ["A", "B"]
    assert loop.queue == []


def test_start_twice_builds_each_section_once(loop, built):
    builder = _builder(loop, _deferred("A", built), _deferred("B", built))

    builder.start()
    builder.start()
    loop.drain()

    assert built == ["A", "B"]


def test_a_section_built_on_demand_is_not_built_again(loop, built):
    first, second = _deferred("A", built), _deferred("B", built)
    builder = _builder(loop, first, second)

    builder.start()
    builder.build(second)
    loop.drain()

    assert built == ["B", "A"]


def test_an_early_request_is_applied_when_its_section_builds(loop, built):
    deferred = _deferred("Camera Controls", built)
    builder = _builder(loop, deferred)
    applied = []

    builder.when_built(deferred, lambda section: applied.append(section.title))

    assert applied == []

    builder.start()
    loop.drain()

    assert applied == ["Camera Controls"]
    assert deferred.state == SECTION_BUILT


def test_a_request_to_a_built_section_is_applied_at_once(loop, built):
    deferred = _deferred("Paths", built)
    builder = _builder(loop, deferred)
    builder.start()
    loop.drain()
    applied = []

    builder.when_built(deferred, lambda section: applied.append(section))

    assert applied == [deferred.section]


def test_waiting_callbacks_run_in_registration_order(loop, built):
    deferred = _deferred("A", built)
    builder = _builder(loop, deferred)
    order = []

    for name in ("wire", "first request", "second request"):
        builder.when_built(deferred, lambda section, name=name: order.append(name))

    builder.start()
    loop.drain()

    assert order == ["wire", "first request", "second request"]


def test_a_failing_build_is_logged_and_does_not_stop_the_others(loop, built):
    failing = _deferred("Zones", built, error=RuntimeError("no zones"))
    builder = _builder(loop, _deferred("Paths", built), failing, _deferred("C", built))
    failures = []
    builder.when_built(failing, lambda section: None, failures.append)

    with patch(CONTENT_LOGGER) as logger:
        builder.start()
        loop.drain()

    logger.error.assert_called_once()
    assert built == ["Paths", "C"]
    assert failing.state == SECTION_FAILED
    assert failing.section is None
    assert failures == ["no zones"]


def test_a_failed_section_says_why_instead_of_loading(loop, built):
    failing = _deferred("Zones", built, error=RuntimeError("no zones"))

    assert failing.status_text == "Loading Zones…"

    with patch(CONTENT_LOGGER):
        _builder(loop, failing).build(failing)

    assert failing.status_text == "Zones could not be loaded: no zones"


def test_a_request_to_a_failed_section_fails_at_once(loop, built):
    failing = _deferred("Zones", built, error=ValueError("bad"))
    builder = _builder(loop, failing)

    with patch(CONTENT_LOGGER):
        builder.build(failing)

    failures = []
    builder.when_built(failing, lambda section: None, failures.append)

    assert failures == ["bad"]


def test_a_raising_callback_does_not_keep_the_others_from_running(loop, built):
    deferred = _deferred("A", built)
    builder = _builder(loop, deferred)
    applied = []

    def raise_error(section):
        raise RuntimeError("callback")

    builder.when_built(deferred, raise_error)
    builder.when_built(deferred, lambda section: applied.append(section.title))

    with patch(CONTENT_LOGGER) as logger:
        builder.start()
        loop.drain()

    logger.error.assert_called_once()
    assert applied == ["A"]


def test_finished_fires_once_after_the_last_section(loop, built):
    builder = _builder(loop, _deferred("A", built), _deferred("B", built))
    finished = []
    builder.observe(lambda event: finished.append(list(built)), "finished")

    builder.start()
    loop.drain()

    assert finished == [["A", "B"]]


def test_sections_start_loading(built):
    assert _deferred("A", built).state == SECTION_LOADING
