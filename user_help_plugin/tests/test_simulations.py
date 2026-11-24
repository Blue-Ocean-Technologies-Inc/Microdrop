# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The simulation catalog reads tutorial pages off the GUI thread, each page
once, and lists only the latest search's outcome."""

# Third-party imports.
import pytest

# Microdrop package imports.
from user_help_plugin import simulations
from user_help_plugin.consts import TutorialEntry
from user_help_plugin.menus import TutorialCatalog
from user_help_plugin.simulations import TutorialSimulationCatalog

PAGE = '<h2>{title}</h2><figure data-demo="{demo}"></figure>'


class InlineThread:
    """``threading.Thread`` that runs its target on this thread when started."""

    def __init__(self, target, args=(), **kwargs):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)


class FakeEventLoop:
    """``GUI.invoke_later`` as a queue the test drains."""

    def __init__(self):
        self.calls = []

    def invoke_later(self, callable, *args, **kwargs):
        self.calls.append((callable, args, kwargs))

    def drain(self):
        while self.calls:
            callable, args, kwargs = self.calls.pop(0)
            callable(*args, **kwargs)


@pytest.fixture
def event_loop(monkeypatch):
    loop = FakeEventLoop()
    monkeypatch.setattr(simulations, "GUI", loop)
    monkeypatch.setattr(simulations, "Thread", InlineThread)

    return loop


@pytest.fixture
def pages_read(monkeypatch):
    """Count the reads of each tutorial page, by title."""
    reads = []
    find_simulations = simulations.find_simulations

    def counting_find_simulations(tutorial):
        reads.append(tutorial.title)

        return find_simulations(tutorial)

    monkeypatch.setattr(simulations, "find_simulations", counting_find_simulations)

    return reads


def _entry(tmp_path, title):
    path = tmp_path / f"{title}.html"
    path.write_text(PAGE.format(title=title, demo=f"{title}-demo"), encoding="utf-8")

    return TutorialEntry(title=title, path=path)


def test_each_page_is_read_once_and_listed_on_the_gui_turn(
    tmp_path, event_loop, pages_read
):
    first, second = _entry(tmp_path, "First"), _entry(tmp_path, "Second")
    tutorial_catalog = TutorialCatalog(entries=[first])
    catalog = TutorialSimulationCatalog(tutorial_catalog=tutorial_catalog)

    catalog.active = True

    # Read already, listed only once the event loop runs the hand-off.
    assert pages_read == ["First"]
    assert catalog.tutorials == []

    event_loop.drain()

    assert [record.tutorial for record in catalog.tutorials] == [first]

    tutorial_catalog.entries = [first, second]
    event_loop.drain()

    assert pages_read == ["First", "Second"]
    assert [record.tutorial for record in catalog.tutorials] == [first, second]
    assert catalog.tutorials[1].simulations[0].demo == "Second-demo"


def test_an_earlier_search_does_not_replace_a_later_ones_list(tmp_path, event_loop):
    first, second = _entry(tmp_path, "First"), _entry(tmp_path, "Second")
    tutorial_catalog = TutorialCatalog(entries=[first, second])
    catalog = TutorialSimulationCatalog(tutorial_catalog=tutorial_catalog)

    catalog.active = True
    tutorial_catalog.entries = [second]
    event_loop.drain()

    assert [record.tutorial for record in catalog.tutorials] == [second]
