# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Build deferred content the first time its place is on screen (#1085).

The trigger is the first paint of the content's place, not a visibility
flag: a dock widget behind another tab counts as visible to Qt (and to
pyface's ``DockPane.visible``) and its widgets even get a show event, but
it is never painted. Nor are the panes Qt shows for a moment while it
restores a window state. A paint means the place really is on screen — a
tab raised, a pane opened from the View menu, floated, or placed by a
layout.

The paint schedules the build on a paced turn (``microdrop_utils.
gui_pacing``), so the frame showing the loading state reaches the screen
first. By then the place may be hidden again (the window raises the
active tab of a restored layout on a zero timer, after a first frame may
have painted the tab Qt made current); the turn checks, and waits for the
next paint if so.

Qt-free: painting, exposure and the paced turn are injected callables.
"""

# Enthought library imports.
from traits.api import Bool, Callable, HasTraits, Instance

# Local imports.
from .deferred_content import CONTENT_LOADING, DeferredContent
from .gui_pacing import invoke_paced


class FirstShowBuilder(HasTraits):
    """Build a deferred content once its place has been painted on screen."""

    #: The content to build.
    contents = Instance(DeferredContent)

    #: ``watch_first_paint(callback)`` calls ``callback()`` once, after the
    #: content's place next paints.
    watch_first_paint = Callable()

    #: Returns whether the content's place is on screen now.
    is_exposed = Callable()

    #: Runs a callable on a later, paced GUI turn.
    invoke_later = Callable()

    #: True once the place is gone; nothing is built after that.
    disposed = Bool(False)

    def _invoke_later_default(self):
        return invoke_paced

    def start(self):
        """Build the content after its place first paints on screen."""
        self.watch_first_paint(self._painted)

    def ensure_built(self):
        """Build the content now, shown or not (for code that needs it)."""

        if not self.disposed:
            self.contents.build_content()

    def dispose(self):
        """The place is gone: build nothing more."""
        self.disposed = True

    def _painted(self):

        if self._still_to_build():
            self.invoke_later(self._build_if_exposed)

    def _build_if_exposed(self):

        if not self._still_to_build():
            return

        if self.is_exposed():
            self.contents.build_content()
        else:
            self.watch_first_paint(self._painted)

    def _still_to_build(self):
        return not self.disposed and self.contents.state == CONTENT_LOADING
