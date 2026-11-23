# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The ML calibration macro judges each reply as the vendor UI does: the
HV_ENABLE and CAP_CALIBRATE_ML status bytes count, a BUSY fit is reported
as a retry, and a failed setup step skips to the teardown, which always
runs. Hardware-free, no Redis."""

# Standard library imports.
import json
import threading

# Third-party imports.
import pytest
from dropbot_portable.portable_dropbot_service import CmdStatus, CommandResult
from dropbot_portable.proxy import (
    SignalBoardCAP_CALIBRATE_MLResponse,
    SignalBoardCmd,
    SignalBoardHV_ENABLEResponse,
)

# Enthought library imports.
from traits.api import Any, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.services import (
    portable_dropbot_calibration_mixin_service as calibration_service,
)
from portable_dropbot_controller.services import (
    portable_dropbot_states_setting_mixin_service as states_service,
)

STAGES = [
    "clear electrodes",
    "release pogos",
    "set 100 V / 10000 Hz",
    "enable HV (bypass)",
    "re-clear electrodes",
    "multi-slope calibration",
    "disable HV",
    "restore V/F",
    "press pogos",
]


class _Uart:
    board_channels = 120

    def __init__(self):
        self.last = None

    def setElectrodeStates(self, states):
        return True

    def setPogo(self, state):
        return bytes([state])

    def last_result(self, cmd=None):
        return self.last


class _Sig:
    def __init__(self, uart, hv_on_status=0, calibrate=1):
        self.uart = uart
        self.hv_on_status = hv_on_status
        self.calibrate = calibrate

    def hv_enable(self, enable, bypass):
        status = self.hv_on_status if enable else 1

        return SignalBoardHV_ENABLEResponse(status=status)

    def cap_calibrate_ml(self, hv_mv):
        if self.calibrate == CmdStatus.BUSY:
            self.uart.last = CommandResult(
                SignalBoardCmd.CAP_CALIBRATE_ML, CmdStatus.BUSY
            )
            return None

        return SignalBoardCAP_CALIBRATE_MLResponse(status=self.calibrate)


class _Session:
    def __init__(self, **sig):
        self.uart = _Uart()
        self.sig = _Sig(self.uart, **sig)

    def set_actuation(self, voltage, frequency):
        return float(voltage)


class _Base(HasTraits):
    proxy = Any()
    _proxy_lock = Any()

    def __proxy_lock_default(self):
        return threading.RLock()

    def _proxy_call(self, context, call):
        return True, call()

    def _apply_actuation(self):
        pass


class _Harness(
    calibration_service.PortableDropbotCalibrationMixinService,
    states_service.PortableDropbotStatesSettingMixinService,
    _Base,
):
    pass


@pytest.fixture
def published(monkeypatch):
    sent = []
    monkeypatch.setattr(
        calibration_service,
        "publish_message",
        lambda topic, message: sent.append(json.loads(message)),
    )

    return sent


def _run(published, **sig):
    harness = _Harness()
    harness.proxy = _Session(**sig)
    harness.on_run_cap_calibration_request("")

    return [update["stage"] for update in published[:-1]], published[-1]


def test_a_clean_run_answers_ok(published):
    stages, done = _run(published)

    assert stages == STAGES
    assert done == {"stage": "done", "ok": True, "error": "", "retry": False}


def test_a_busy_fit_is_a_retry_and_the_teardown_runs(published):
    stages, done = _run(published, calibrate=CmdStatus.BUSY)

    assert stages == STAGES
    assert done["ok"] is False and done["retry"] is True
    assert "BUSY, retry" in done["error"]


def test_a_fit_that_is_not_done_fails(published):
    _stages, done = _run(published, calibrate=0)

    assert done["ok"] is False and done["retry"] is False
    assert "status 0 (not done)" in done["error"]


def test_a_refused_hv_enable_skips_to_the_teardown(published):
    stages, done = _run(published, hv_on_status=2)

    assert stages == STAGES[:4] + STAGES[6:]
    assert done["ok"] is False
    assert "no device on the pads" in done["error"]
