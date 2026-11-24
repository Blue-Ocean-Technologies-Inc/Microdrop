# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Content builds on a paced turn after its place first paints, only if the
place is still on screen then (else it waits for the next paint), once, and
never after its place is gone. No Qt: paints, exposure and the paced queue
are driven by the tests."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.deferred_content import (
    CONTENT_BUILT,
    CONTENT_LOADING,
    DeferredContent,
)
from microdrop_utils.first_show_builder import FirstShowBuilder


class Screen:
    """The content's place: paint watchers, whether it is shown, and the
    paced queue."""

    def __init__(self):
        self.exposed = False
        self.paint_watchers = []
        self.turns = []

    def watch_first_paint(self, callback):
        self.paint_watchers.append(callback)

    def paint(self):
        watchers, self.paint_watchers = self.paint_watchers, []

        for callback in watchers:
            callback()

    def invoke_later(self, function):
        self.turns.append(function)

    def drain(self):
        while self.turns:
            self.turns.pop(0)()


@pytest.fixture
def screen():
    return Screen()


@pytest.fixture
def builds():
    return []


@pytest.fixture
def builder(screen, builds):
    contents = DeferredContent(title="Log", build=lambda: builds.append("Log"))
    builder = FirstShowBuilder(
        contents=contents,
        watch_first_paint=screen.watch_first_paint,
        is_exposed=lambda: screen.exposed,
        invoke_later=screen.invoke_later,
    )
    builder.start()

    return builder


def test_nothing_builds_before_the_first_paint(screen, builds, builder):
    screen.exposed = True
    screen.drain()

    assert builds == []
    assert builder.contents.state == CONTENT_LOADING


def test_the_first_paint_builds_on_a_later_turn(screen, builds, builder):
    screen.exposed = True
    screen.paint()

    assert builds == []

    screen.drain()

    assert builds == ["Log"]
    assert builder.contents.state == CONTENT_BUILT


def test_a_place_hidden_again_by_the_turn_waits_for_its_next_paint(
    screen, builds, builder
):
    # Painted in a first frame, then sent behind the tab the layout raises.
    screen.paint()
    screen.drain()

    assert builds == []
    assert len(screen.paint_watchers) == 1

    screen.exposed = True
    screen.paint()
    screen.drain()

    assert builds == ["Log"]


def test_later_paints_build_nothing_more(screen, builds, builder):
    screen.exposed = True
    screen.paint()
    screen.drain()
    screen.paint()
    screen.drain()

    assert builds == ["Log"]
    assert screen.paint_watchers == []


def test_ensure_built_builds_an_unshown_place_once(screen, builds, builder):
    builder.ensure_built()
    screen.exposed = True
    screen.paint()
    screen.drain()

    assert builds == ["Log"]


def test_a_disposed_place_builds_nothing(screen, builds, builder):
    screen.exposed = True
    screen.paint()
    builder.dispose()
    screen.drain()
    builder.ensure_built()

    assert builds == []


def test_a_failed_build_is_not_retried_on_the_next_paint(screen):
    attempts = []

    def build():
        attempts.append("tried")
        raise RuntimeError("broken")

    builder = FirstShowBuilder(
        contents=DeferredContent(title="Log", build=build),
        watch_first_paint=screen.watch_first_paint,
        is_exposed=lambda: True,
        invoke_later=screen.invoke_later,
    )
    builder.start()
    screen.paint()
    screen.drain()
    screen.paint()
    screen.drain()

    assert attempts == ["tried"]
    assert screen.paint_watchers == []
