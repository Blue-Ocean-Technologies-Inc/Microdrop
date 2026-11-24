# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The content of a deferred sidebar section's box: a muted loading line
until the section is built, then the section's widget in its place (#1064).

The box and its header exist from the first paint, so the section keeps its
place; a failed build turns the line into the reason, so it never reads as
loading forever.
"""

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QLabel
from traits.api import HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import CollapsibleVStackBox

# Local imports.
from ...models.deferred_sidebar_section import (
    SECTION_BUILT,
    SECTION_FAILED,
    DeferredSidebarSection,
)

#: Same side margins as the camera controls' rows, so the line sits where
#: the content will start.
STATUS_LINE_MARGINS = (11, 6, 11, 6)


class DeferredSectionContent(HasTraits):
    """Shows a deferred section's status in its box until it is built."""

    #: The section the box stands for.
    section = Instance(DeferredSidebarSection)

    #: The section's collapsible box.
    box = Instance(CollapsibleVStackBox)

    #: The loading (or failure) line; None once the content is in.
    status_line = Instance(QLabel)

    def traits_init(self):
        self.status_line = QLabel(self.section.status_text)
        self.status_line.setWordWrap(True)
        self.status_line.setContentsMargins(*STATUS_LINE_MARGINS)

        # Disabled, like the Camera Properties loading line, so it reads
        # as muted text.
        self.status_line.setEnabled(False)

        self.box.content_layout.addWidget(self.status_line)
        self.box.content_widgets = [self.status_line]

        self._show_state()

    @observe("section:status_text")
    def _show_status_text(self, event):

        if self.status_line is not None:
            self.status_line.setText(event.new)

    @observe("section:state")
    def _show_state(self, event=None):
        state = self.section.state

        if state == SECTION_FAILED:
            self.status_line.setEnabled(True)
            self.status_line.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.status_line.setStyleSheet(f"color: {ERROR_COLOR};")

        elif state == SECTION_BUILT:
            self._swap_in(self.section.section.widget)

    def _swap_in(self, widget):
        """Put the built section's widget where the status line was."""
        layout = self.box.content_layout

        layout.removeWidget(self.status_line)
        self.status_line.deleteLater()
        self.status_line = None

        layout.addWidget(widget)
        widget.setVisible(True)
        self.box.content_widgets = [widget]


def build_deferred_section_box(section):
    """The collapsible box of a deferred section, showing its status until
    the section is built."""
    box = CollapsibleVStackBox(section.title, control_widgets=None)

    # Held by the box, which lives as long as the sidebar does.
    box.deferred_content = DeferredSectionContent(section=section, box=box)

    return box
