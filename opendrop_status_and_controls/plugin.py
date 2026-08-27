# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from template_status_and_controls.base_plugin import BaseStatusPlugin

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT


class OpendropStatusAndControlsPlugin(BaseStatusPlugin):
    """Envisage plugin for OpenDrop status display and controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import OpendropStatusAndControls
        return OpendropStatusAndControls

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT
