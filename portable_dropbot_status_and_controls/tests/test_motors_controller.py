# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A Move By preset publishes exactly the manual Move By request.
publish_message is patched; no Redis."""

# Standard library imports.
import json

# Microdrop package imports.
from portable_dropbot_controller.consts import MOTOR_MOVE
from portable_dropbot_status_and_controls.controllers import motors_controller
from portable_dropbot_status_and_controls.models.motors_model import (
    PortableDropbotMotorsModel,
)


def test_move_preset_publishes_the_manual_move(monkeypatch):
    sent = []
    monkeypatch.setattr(
        motors_controller,
        "publish_message",
        lambda topic, message: sent.append((topic, json.loads(message))),
    )
    model = PortableDropbotMotorsModel(selected_motor="pmt", move_presets=[-1.0, 2.5])
    # Held: the model's observers only weakly reference their controller.
    _controller = motors_controller.MotorsController(model)

    model.move_by_mm = 2.5
    model.move_by_button = True

    # What the preset button does: set the distance, then fire Go.
    model.move_by_mm = model.move_presets[1]
    model.move_by_button = True

    manual = (MOTOR_MOVE, {"motor": "pmt", "mode": "relative", "value": 2500})

    assert sent == [manual, manual]
