# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A sidebar section whose content is built after the main window's first
paint (#1064).

Qt-free: the section holds its place in the sidebar (title, collapsed) from
the start, and says whether its content is still loading, is in, or failed
to build.
"""

# Enthought library imports.
from traits.api import Callable, Enum, Instance, Property, Str

# Local imports.
from ..interfaces.descriptors import SidebarSection

SECTION_LOADING = "loading"
SECTION_BUILT = "built"
SECTION_FAILED = "failed"


class DeferredSidebarSection(SidebarSection):
    """A sidebar section built later, in place of the one it stands for.

    ``widget`` stays None: the sidebar shows ``status_text`` in the
    section's box until ``section`` is built, then the built section's
    widget.
    """

    #: Builds and returns the real SidebarSection.
    build = Callable()

    #: Where the build stands.
    state = Enum(SECTION_LOADING, SECTION_BUILT, SECTION_FAILED)

    #: The built section; None until it is built.
    section = Instance(SidebarSection)

    #: Why the build failed; empty otherwise.
    error = Str()

    #: What the box shows in place of the content: loading, or why it failed.
    status_text = Property(Str, observe="title, state, error")

    def _get_status_text(self):
        if self.state == SECTION_FAILED:
            return f"{self.title} could not be loaded: {self.error}"

        return f"Loading {self.title}…"
