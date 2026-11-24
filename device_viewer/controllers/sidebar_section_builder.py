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

The window repaints and takes input between turns, so the sections fill in
instead of holding up the main window. Code that needs a section before it
exists asks ``when_built``: it runs at once for a built section, or when
the section is built — or, should its build fail, its failure callback
runs instead, so no request waits forever.

Qt-free: turns are scheduled with ``pyface.api.GUI.invoke_later``.
"""

# Enthought library imports.
from pyface.api import GUI
from traits.api import Bool, Callable, Dict, Event, HasTraits, Instance, List

# Local imports.
from ..models.deferred_sidebar_section import (
    SECTION_BUILT,
    SECTION_FAILED,
    SECTION_LOADING,
    DeferredSidebarSection,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SidebarSectionBuilder(HasTraits):
    """Build deferred sidebar sections in order, each once."""

    #: The sections to build, in the order they are built.
    sections = List(Instance(DeferredSidebarSection))

    #: Runs a callable on a later event-loop turn.
    invoke_later = Callable()

    #: True once ``start`` has scheduled the first turn.
    started = Bool(False)

    #: Fired once every section is built or has failed.
    finished = Event()

    #: (on_built, on_failed) pairs waiting on each section still loading.
    _waiting = Dict()

    def _invoke_later_default(self):
        return GUI.invoke_later

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

        if deferred.state == SECTION_BUILT:
            on_built(deferred.section)

        elif deferred.state == SECTION_FAILED:
            if on_failed is not None:
                on_failed(deferred.error)

        else:
            self._waiting.setdefault(deferred, []).append((on_built, on_failed))

    def build(self, deferred):
        """Build ``deferred`` now, unless it is built or has failed already."""

        if deferred.state != SECTION_LOADING:
            return

        try:
            section = deferred.build()
        except Exception as error:
            logger.error(
                f"Device viewer sidebar section {deferred.title!r} could not "
                f"be built: {error}",
                exc_info=True,
            )
            deferred.error = str(error) or type(error).__name__
            deferred.state = SECTION_FAILED
            self._notify(deferred, failed=True)

            return

        deferred.section = section
        deferred.state = SECTION_BUILT
        self._notify(deferred, failed=False)

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

    def _notify(self, deferred, failed):
        """Run the callbacks waiting on ``deferred``; one that raises is
        logged and does not keep the others from running."""

        for on_built, on_failed in self._waiting.pop(deferred, []):
            callback, argument = (
                (on_failed, deferred.error) if failed else (on_built, deferred.section)
            )

            if callback is None:
                continue

            try:
                callback(argument)
            except Exception as error:
                logger.error(
                    f"Waiting on sidebar section {deferred.title!r}: {error}",
                    exc_info=True,
                )
