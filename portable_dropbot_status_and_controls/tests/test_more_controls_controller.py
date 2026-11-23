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
Target requests, and a heater auto-tune proposal is written only after the
confirm. publish_message and the publishers are patched; no Redis."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.api import NO, YES

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    PMT_SET_GAIN,
    TEMP_SET_TARGET,
    HeaterTuneApplyRequest,
    HeaterTuneDone,
)
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


# --------------------------------------------------------------------- #
# Heater auto-tune: Apply asks first                                     #
# --------------------------------------------------------------------- #

DONE = {
    "channel": 1,
    "ok": True,
    "reason": "plateau reached",
    "fit": {
        "gain": 0.5,
        "tau_s": 40.0,
        "dead_time_s": 2.0,
        "r2": 0.99,
        "rmse_c": 0.05,
        "reached": 0.9,
    },
    "proposals": {
        style: {"kp": kp, "ki": 0.1, "kd": 0.0, "lambda_s": 20.0}
        for style, kp in (("smooth", 1.5), ("default", 3.0), ("fast", 6.0))
    },
    "smith_model": [0.5, 40.0, 2.0],
}


class _Publisher:
    def __init__(self):
        self.published = []

    def publish(self, payload):
        self.published.append(HeaterTuneApplyRequest.model_validate(payload))


@pytest.fixture
def tuned(monkeypatch, wired):
    model, controller, _sent = wired
    publisher = _Publisher()
    monkeypatch.setattr(
        more_controls_controller, "heater_tune_apply_publisher", publisher
    )
    model.heater_tune.adopt_done(HeaterTuneDone.model_validate(DONE))

    return model, publisher.published


def _answer(monkeypatch, answer):
    monkeypatch.setattr(more_controls_controller, "confirm", lambda *a, **k: answer)


def test_a_declined_apply_writes_nothing(monkeypatch, tuned):
    model, applied = tuned
    _answer(monkeypatch, NO)

    model.heater_tune.apply_button = True

    assert applied == []


def test_a_confirmed_apply_writes_the_selected_style_to_the_fitted_channel(
    monkeypatch, tuned
):
    model, applied = tuned
    _answer(monkeypatch, YES)
    model.temp_channel = 0
    model.heater_tune.style = "fast"

    model.heater_tune.apply_button = True

    [request] = applied

    assert (request.channel, request.kp, request.persist) == (1, 6.0, False)
    assert request.smith_model == (0.5, 40.0, 2.0)
    assert request.period_ms == 1000
