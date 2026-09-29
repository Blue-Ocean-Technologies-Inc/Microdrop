# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""Assemble the device viewer sidebar from its sections."""

# Enthought library imports.
from pyface.qt.QtWidgets import (
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import CollapsibleVStackBox


def build_sidebar(sections):
    """Stack the sections, in order, as collapsible boxes in a scroll area.

    A ``None`` entry — a layer with nothing to contribute — is skipped.
    The scroll area's ``widget()`` holds the stacked boxes.
    """
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setVisible(True)

    scroll_content = QWidget()
    scroll_layout = QVBoxLayout(scroll_content)

    for section in sections:
        if section is None:
            continue

        box = CollapsibleVStackBox(section.title, control_widgets=section.widget)
        box.set_expanded(not section.collapsed)
        scroll_layout.addWidget(box)

    scroll_layout.addStretch()
    scroll_area.setWidget(scroll_content)

    return scroll_area


def build_reveal_button(scroll_area):
    """Build the narrow button that shows and hides the sidebar."""
    reveal_button = QPushButton("chevron_right")
    reveal_button.setToolTip("Reveal Hidden Controls")
    reveal_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

    def toggle_sidebar():
        is_now_visible = not scroll_area.isVisible()
        scroll_area.setVisible(is_now_visible)

        # The chevron points the way the next click moves the sidebar.
        reveal_button.setText("chevron_right" if is_now_visible else "chevron_left")

    reveal_button.clicked.connect(toggle_sidebar)

    return reveal_button
