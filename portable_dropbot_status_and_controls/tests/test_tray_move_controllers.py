# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The tray controls publish MOVE_TRAY through the validated publisher: the
status pane's glyph moves the tray only, its device picture runs the pogo
pushpad macro, and the motors pane follows its Tray only checkbox. The
publishers are patched; no Redis."""

# Microdrop package imports.
from portable_dropbot_status_and_controls.controllers import (
    motors_controller,
)
from portable_dropbot_status_and_controls.controllers import (
    status_controls_pane_controller as status_controller,
)
from portable_dropbot_status_and_controls.models.model import (
    PortableDropbotStatusAndControlsModel,
)
from portable_dropbot_status_and_controls.models.motors_model import (
    PortableDropbotMotorsModel,
)


def _capture_tray_publishes(monkeypatch, module):
    sent = []
    monkeypatch.setattr(
        module.move_tray_publisher, "publish", lambda payload, **_: sent.append(payload)
    )
    monkeypatch.setattr(module, "publish_message", lambda **_: None)

    return sent


def test_status_glyph_moves_the_tray_only(monkeypatch):
    sent = _capture_tray_publishes(monkeypatch, status_controller)
    model = PortableDropbotStatusAndControlsModel()
    # Held: the model's observers only weakly reference their controller.
    _controller = status_controller.PortableDropbotStatusAndControlsController(model)

    model.tray_out = True

    assert sent == [{"direction": "out", "actuate_pogos": False}]


def test_status_picture_click_runs_the_pogo_macro(monkeypatch):
    sent = _capture_tray_publishes(monkeypatch, status_controller)
    model = PortableDropbotStatusAndControlsModel()
    _controller = status_controller.PortableDropbotStatusAndControlsController(model)
    model.connected = True

    model.tray_toggle_clicked = True

    assert sent == [{"direction": "toggle", "actuate_pogos": True}]


def test_motors_tray_macros_follow_the_tray_only_checkbox(monkeypatch):
    sent = _capture_tray_publishes(monkeypatch, motors_controller)
    model = PortableDropbotMotorsModel(selected_motor="tray")
    _controller = motors_controller.MotorsController(model)

    model.macro_button_2 = True
    model.tray_only = True
    model.macro_button_1 = True

    assert sent == [
        {"direction": "out", "actuate_pogos": True},
        {"direction": "in", "actuate_pogos": False},
    ]
