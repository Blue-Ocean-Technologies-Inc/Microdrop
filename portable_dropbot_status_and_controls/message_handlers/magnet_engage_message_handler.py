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
from pyface.api import GUI
from traits.api import Instance, Str

# Microdrop package imports.
from portable_dropbot_controller.consts import MagnetEngageUpdated
from template_status_and_controls.base_message_handler import BaseMessageHandler

# Local imports.
from ..consts import MAGNET_ENGAGE_LISTENER
from ..models.magnet_engage_model import MagnetEngageModel


class PortableDropbotMagnetEngageMessageHandler(BaseMessageHandler):
    """Feeds MAGNET_ENGAGE_UPDATED to the plugin's MagnetEngageModel, which
    the Portable DropBot Settings preferences tab shows."""

    model = Instance(MagnetEngageModel)

    name = Str(MAGNET_ENGAGE_LISTENER)

    def _on_magnet_engage_updated_triggered(self, body):
        update = MagnetEngageUpdated.model_validate_json(str(body))

        # Handlers run on the Dramatiq worker thread; the model's observers
        # update an open preferences dialog, so they must run on the GUI one.
        GUI.invoke_later(self.model.apply_update, update)
