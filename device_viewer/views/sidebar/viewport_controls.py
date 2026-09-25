# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""Sidebar section: viewport zoom and fit controls."""

# Local imports.
from ..viewport_settings_view.widget import ZoomControlWidget, ZoomViewModel
from .section import SidebarSection


def build_viewport_controls(model):
    """Build the Viewport Controls section for the main model."""
    vm = ZoomViewModel(model=model)

    return SidebarSection(title="Viewport Controls", widget=ZoomControlWidget(vm))
