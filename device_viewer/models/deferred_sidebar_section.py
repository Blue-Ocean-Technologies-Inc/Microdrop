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
to build — the deferred content's state.
"""

# Enthought library imports.
from traits.api import Instance, Property

# Microdrop utils imports.
from microdrop_utils.deferred_content import (
    CONTENT_BUILT,
    CONTENT_FAILED,
    CONTENT_LOADING,
    DeferredContent,
)

# Local imports.
from ..interfaces.descriptors import SidebarSection

SECTION_LOADING = CONTENT_LOADING
SECTION_BUILT = CONTENT_BUILT
SECTION_FAILED = CONTENT_FAILED


class DeferredSidebarSection(DeferredContent, SidebarSection):
    """A sidebar section built later, in place of the one it stands for.

    ``widget`` stays None: the sidebar shows ``status_text`` in the
    section's box until ``section`` is built, then the built section's
    widget.
    """

    #: The built section; None until it is built.
    section = Property(Instance(SidebarSection), observe="content")

    def _get_section(self):
        return self.content

    def _set_section(self, section):
        self.content = section
