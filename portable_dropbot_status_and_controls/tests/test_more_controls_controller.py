# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Gain and heater-target presets publish exactly the manual Set Gain / Set
Target requests. publish_message is patched; no Redis."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import PMT_SET_GAIN, TEMP_SET_TARGET
from portable_dropbot_status_and_controls.controllers import (
    more_controls_controller,
)
from portable_dropbot_status_and_controls.models.more_controls_model import (
    PortableDropbotMoreControlsModel,
)


@pytest.fixture
def wired(monkeypatch):
    sent = []
    monkeypatch.setattr(
        more_controls_controller,
        "publish_message",
        lambda topic, message: sent.append((topic, message)),
    )
    model = PortableDropbotMoreControlsModel(
        gain_presets=[64, 200], temperature_presets=[37.0, 55.5]
    )
    # Held: the model's observers only weakly reference their controller.
    controller = more_controls_controller.MoreControlsController(model)

    return model, controller, sent


def test_gain_preset_publishes_the_manual_gain(wired):
    model, _controller, sent = wired

    model.pmt_gain = 200
    model.set_gain_button = True

    # What the preset button does: set the gain, then fire Set Gain.
    model.pmt_gain = model.gain_presets[1]
    model.set_gain_button = True

    assert sent == [(PMT_SET_GAIN, "200"), (PMT_SET_GAIN, "200")]


def test_temperature_preset_publishes_the_manual_target(wired):
    model, _controller, sent = wired
    model.temp_channel = 1

    model.temp_target_c = 55.5
    model.set_target_button = True

    # What the preset button does: set the target, then fire Set Target.
    model.temp_target_c = model.temperature_presets[1]
    model.set_target_button = True

    manual = (TEMP_SET_TARGET, {"channel": 1, "target_c": 55.5})

    assert [(topic, json.loads(message)) for topic, message in sent] == [
        manual,
        manual,
    ]
