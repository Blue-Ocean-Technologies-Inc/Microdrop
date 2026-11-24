# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The interactive simulations inside the Help > Tutorials pages.

Every ``<figure data-demo>`` of a built tutorial page is one simulation.
The Tutorial Simulations pane loads each page once and shows one figure at
a time (``resources/show_simulation.js``), so every simulation gets its own
tab without a second copy of any of them.

The pages are several megabytes of HTML together, so they are read on a
worker thread, each once.
"""

# Standard library imports.
from html.parser import HTMLParser
from threading import Thread

# Enthought library imports.
from pyface.api import GUI
from traits.api import (
    Bool,
    Dict,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
    observe,
)

# Local imports.
from .consts import TutorialEntry
from .menus import TutorialCatalog

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

HEADING_TAGS = {"h2", "h3"}

#: A heading's ``<span class="where">`` note is not part of its title.
HEADING_NOTE_CLASS = "where"

#: Dropped from a tutorial's title in its tab label, where it is noise.
TUTORIAL_TITLE_SUFFIX = " Tutorial"


class TutorialSimulation(HasTraits):
    """One simulation: a ``<figure data-demo>`` of a tutorial page."""

    #: The figure's ``data-demo`` name, unique within its page.
    demo = Str()

    #: Tab label: the figure's ``data-title``, else the heading above it.
    title = Str()


class TutorialSimulations(HasTraits):
    """The simulations of one tutorial page, in page order."""

    #: The tutorial the simulations come from.
    tutorial = Instance(TutorialEntry)

    simulations = List(Instance(TutorialSimulation))

    #: Tab label: the tutorial's title without its " Tutorial" suffix.
    label = Property(Str, observe="tutorial.title")

    def _get_label(self):
        return self.tutorial.title.removesuffix(TUTORIAL_TITLE_SUFFIX)


class _SimulationFinder(HTMLParser):
    """Collect ``(demo, title)`` for every ``<figure data-demo>``."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []
        self._heading = ""
        self._heading_tag = None
        self._heading_text = []
        self._note_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if tag in HEADING_TAGS:
            self._heading_tag = tag
            self._heading_text = []

        elif self._heading_tag and tag == "span":
            classes = (attributes.get("class") or "").split()

            if self._note_depth or HEADING_NOTE_CLASS in classes:
                self._note_depth += 1

        elif tag == "figure" and attributes.get("data-demo"):
            title = attributes.get("data-title") or self._heading
            self.found.append((attributes["data-demo"], title))

    def handle_endtag(self, tag):
        if tag == self._heading_tag:
            self._heading = " ".join("".join(self._heading_text).split())
            self._heading_tag = None

        elif tag == "span" and self._note_depth:
            self._note_depth -= 1

    def handle_data(self, data):
        if self._heading_tag and not self._note_depth:
            self._heading_text.append(data)


def find_simulations(tutorial):
    """Return the ``TutorialSimulations`` of one tutorial page.

    A page that cannot be read gives none, so one broken tutorial never
    hides the others' simulations.
    """

    try:
        page = tutorial.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        logger.error(f"Cannot read tutorial page {tutorial.path}: {error}")
        page = ""

    finder = _SimulationFinder()
    finder.feed(page)
    finder.close()

    simulations = []
    title_counts = {}

    for demo, title in finder.found:
        title = title or demo
        title_counts[title] = title_counts.get(title, 0) + 1

        # Two figures under one heading still need tell-apart tabs.
        if title_counts[title] > 1:
            title = f"{title} ({title_counts[title]})"

        simulations.append(TutorialSimulation(demo=demo, title=title))

    return TutorialSimulations(tutorial=tutorial, simulations=simulations)


class TutorialSimulationCatalog(HasTraits):
    """Every tutorial's simulations, following the tutorial catalog."""

    #: The Help > Tutorials catalog the simulations are found in.
    tutorial_catalog = Instance(TutorialCatalog, ())

    #: One record per tutorial that has simulations, in catalog order.
    tutorials = List(Instance(TutorialSimulations))

    #: Whether anything shows the simulations yet. The pages are read only
    #: from then on, so a pane that stays hidden costs nothing at launch.
    active = Bool(False)

    #: The simulations of every page read so far, by tutorial entry: a
    #: catalog change reads only the pages new to it.
    _found = Dict()

    #: Number of the latest search; an earlier one only adds its pages.
    _search = Int(0)

    @observe("tutorial_catalog.entries, active")
    def _find_simulations(self, event):
        if not self.active:
            return

        entries = list(self.tutorial_catalog.entries)
        unread = [entry for entry in entries if entry not in self._found]
        self._search += 1

        if not unread:
            self._show(self._search, entries, {})

            return

        Thread(
            target=self._read_pages,
            args=(self._search, entries, unread),
            name="tutorial simulations",
            daemon=True,
        ).start()

    def _read_pages(self, search, entries, unread):
        """Read the ``unread`` pages, on the worker thread, and show the
        outcome on the GUI thread."""
        found = {entry: find_simulations(entry) for entry in unread}

        GUI.invoke_later(self._show, search, entries, found)

    def _show(self, search, entries, found):
        """Keep the pages ``found``; list ``entries``' simulations, unless a
        later search will."""
        self._found.update(found)

        if search != self._search:
            return

        records = [self._found[entry] for entry in entries]

        self.tutorials = [record for record in records if record.simulations]
