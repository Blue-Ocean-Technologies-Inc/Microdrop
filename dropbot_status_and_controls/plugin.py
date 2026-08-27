# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# from pyface.action.schema.schema_addition import SchemaAddition

from envisage.ids import PREFERENCES_CATEGORIES, PREFERENCES_PANES
from traits.api import List

from template_status_and_controls.base_plugin import BaseStatusPlugin
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class DropbotStatusAndControlsPlugin(BaseStatusPlugin):
    """Envisage plugin for DropBot status display and controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    def _get_dock_pane_class(self):
        from .dock_pane import DropbotStatusAndControlsDockPane
        return DropbotStatusAndControlsDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    def _preferences_panes_default(self):
        from .preferences import DropbotStatusAndControlsPreferencesPane
        return [DropbotStatusAndControlsPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import dropbot_status_and_controls_tab
        return [dropbot_status_and_controls_tab]

    # def _get_menu_additions(self) -> list:
    #     from .menus import menu_factory
    #     return [
    #         SchemaAddition(
    #             factory=menu_factory,
    #             before="TaskToggleGroup",
    #             path="MenuBar/View",
    #         )
    #     ]