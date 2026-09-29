# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""Sidebar section: route layers, execution settings, and the mode picker."""

# Enthought library imports.
from traits.api import Instance
from traitsui.api import UI

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import CollapsibleVStackBox

# Local imports.
from ..mode_picker.widget import ModePicker, ModePickerViewModel
from ..route_selection_view.route_selection_view import (
    ExecutionSettingsView,
    RouteLayerView,
)
from .section import SidebarSection, stack_widgets


class PathsSection(SidebarSection):
    """The Paths section and the parts the pane drives directly."""

    #: Route layer list UI; the pane sizes it from preferences.
    layer_ui = Instance(UI)

    #: Execution settings UI, nested collapsed inside the section.
    execution_settings_ui = Instance(UI)

    #: The nested Execution Settings box.
    execution_settings_box = Instance(CollapsibleVStackBox)

    #: Edit-mode buttons with undo/redo.
    mode_picker_view = Instance(ModePicker)


def build_paths(model, undo, redo):
    """Build the Paths section; `undo` and `redo` back the mode picker's buttons."""
    layer_ui = model.edit_traits(view=RouteLayerView)
    execution_settings_ui = model.edit_traits(view=ExecutionSettingsView)

    _mode_picker_viewmodel = ModePickerViewModel(
        model=model, undo_handler=undo, redo_handler=redo
    )
    mode_picker_view = ModePicker(view_model=_mode_picker_viewmodel)

    execution_settings_box = CollapsibleVStackBox(
        "Execution Settings", control_widgets=execution_settings_ui.control
    )
    execution_settings_box.set_expanded(False)
    execution_settings_box.main_layout.setContentsMargins(12, 0, 0, 0)

    return PathsSection(
        title="Paths",
        widget=stack_widgets(
            [execution_settings_box, layer_ui.control, mode_picker_view]
        ),
        layer_ui=layer_ui,
        execution_settings_ui=execution_settings_ui,
        execution_settings_box=execution_settings_box,
        mode_picker_view=mode_picker_view,
    )
