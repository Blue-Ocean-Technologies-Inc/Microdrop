# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from ..models.motors_model import PortableDropbotMotorsModel


class PortableDropbotMotorsMessageHandler(BaseMessageHandler):
    """Connection handling (inherited) so the panel greys out with
    the device, plus chip presence from the status stream — the
    firmware only moves the magnet with a chip on the pad, and the
    magnet macros grey out to say so."""

    model = Instance(PortableDropbotMotorsModel)

    def _on_status_updated_triggered(self, body):
        data = json.loads(str(body))
        self.model.chip_inserted = bool(data.get("chip_on_pad", False))
