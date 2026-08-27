# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traitsui.menu import Menu, Action

RouteLayerMenu = Menu(
    Action(name="&Execute Path", action="execute_path", enabled_when="not object.execution_disabled"),
    Action(name="&Invert", action="invert_layer"),
    Action(name="&Delete", action="delete_layer"),
    Action(name="&Start Merge", action="start_merge_layer", visible_when="not object.merge_in_progress"), # Note that object in this case refers to the RouteLayer clicked on! No easy way to access main model
    Action(name="&Merge With", action="merge_layer", visible_when="object.merge_in_progress"),
    Action(name="St&op Merging", action="cancel_merge_layer", visible_when="object.merge_in_progress")
)