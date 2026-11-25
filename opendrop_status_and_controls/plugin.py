# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from traits.api import Any

# Microdrop package imports.
from template_status_and_controls.base_plugin import BaseStatusPlugin

# Local imports.
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class OpendropStatusAndControlsPlugin(BaseStatusPlugin):
    """Envisage plugin for OpenDrop status display and controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import OpendropStatusAndControls

        return OpendropStatusAndControls

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    #: The status model and its message listener, made at start: the
    #: listener's routes are registered at launch, so it must exist before
    #: any routed message arrives, not wait for the pane, which shows them.
    status_model = Any()
    message_handler = Any()

    def start(self):
        """Make the Qt-free status model and its message listener."""
        from .message_handler import OpendropStatusAndControlsMessageHandler
        from .model import OpendropStatusAndControlsModel

        self.status_model = OpendropStatusAndControlsModel()
        self.message_handler = OpendropStatusAndControlsMessageHandler(
            model=self.status_model,
            name=f"{PKG}_listener",
        )

    def stop(self):
        """Release the message listener, so a restart can register it anew."""

        if self.message_handler is not None:
            self.message_handler.teardown()
            self.message_handler = None
