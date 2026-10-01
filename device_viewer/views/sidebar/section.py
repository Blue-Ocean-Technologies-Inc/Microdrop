# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""The unit the device viewer sidebar is assembled from.

``SidebarSection`` is part of the layer contract (#650) and lives with it
in ``device_viewer.interfaces``; it is imported here for the built-in
section builders.
"""

# Enthought library imports.
from pyface.qt.QtWidgets import QVBoxLayout, QWidget

# Local imports.
from ...interfaces.descriptors import SidebarSection as SidebarSection


def stack_widgets(widgets):
    """Stack widgets into one container with no margins or spacing.

    The collapsible box lays its content out the same way, so a stacked
    section looks exactly like one whose widgets sit in the box directly.
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setSpacing(0)
    layout.setContentsMargins(0, 0, 0, 0)

    for widget in widgets:
        layout.addWidget(widget)

    return container
