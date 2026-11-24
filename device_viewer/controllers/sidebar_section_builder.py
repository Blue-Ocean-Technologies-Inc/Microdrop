# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Build the deferred device viewer sidebar sections after the first paint,
one per event-loop turn (#1064).

The turns go through the shared paced queue (``microdrop_utils.gui_pacing``),
so the window repaints and takes input between them and the sections fill in
instead of holding up the main window. Code that needs a section before it
exists asks ``when_built``: it runs at once for a built section, or when
the section is built — or, should its build fail, its failure callback
runs instead, so no request waits forever (each section is a
``microdrop_utils.deferred_content.DeferredContent``, which keeps them).

Qt-free: turns are scheduled with ``invoke_paced``.
"""

# Enthought library imports.
from traits.api import Bool, Callable, Event, HasTraits, Instance, List

# Microdrop utils imports.
from microdrop_utils.gui_pacing import invoke_paced

# Local imports.
from ..models.deferred_sidebar_section import SECTION_LOADING, DeferredSidebarSection


class SidebarSectionBuilder(HasTraits):
    """Build deferred sidebar sections in order, each once."""

    #: The sections to build, in the order they are built.
    sections = List(Instance(DeferredSidebarSection))

    #: Runs a callable on a later, paced event-loop turn.
    invoke_later = Callable()

    #: True once ``start`` has scheduled the first turn.
    started = Bool(False)

    #: Fired once every section is built or has failed.
    finished = Event()

    def _invoke_later_default(self):
        return invoke_paced

    def start(self):
        """Build the sections from the next turn on; later calls do nothing."""

        if self.started:
            return

        self.started = True
        self.invoke_later(self._build_next)

    def when_built(self, deferred, on_built, on_failed=None):
        """Call ``on_built(section)`` with ``deferred``'s built section, now
        or once it is built; ``on_failed(error)`` instead if its build fails.
        Callbacks run in the order they were registered."""
        deferred.when_built(on_built, on_failed)

    def build(self, deferred):
        """Build ``deferred`` now, unless it is built or has failed already."""
        deferred.build_content()

    def _build_next(self):
        """Build the next section still loading, then schedule the rest."""
        loading = [
            deferred for deferred in self.sections if deferred.state == SECTION_LOADING
        ]

        if loading:
            self.build(loading[0])

        if len(loading) > 1:
            self.invoke_later(self._build_next)

            return

        self.finished = True
