# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater verify run: the regulated loop always ends with the heater off
(settled, refused set point or loop start, cancel, a lost link), its
metrics are reported, and the verify mixin shares the tune's start rules
and heater ownership. The fakes of ``test_heater_tune`` plus a regulated
loop; hardware-free, no Redis."""

# Standard library imports.
import functools
import json
from types import SimpleNamespace

# Third-party imports.
import pytest
from dropbot_portable.heater_tune import VerifyConfig

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    HEATER_TUNE_VERIFY_PHASE,
    HEATER_TUNE_VERIFY_START,
    TEMP_SET_TARGET,
    HeaterTuneDone,
    HeaterTuneProgress,
    HeaterTuneVerifyDone,
)
from portable_dropbot_controller.heater_tune_capture import (
    CONNECTION_LOST_REASON,
    HeaterTuneCancel,
)
from portable_dropbot_controller.heater_tune_verify import (
    run_verify,
    summarize_verify,
)
from portable_dropbot_controller.services import (
    portable_dropbot_heater_tune_mixin_service as tune_service,
)
from portable_dropbot_controller.services import (
    portable_dropbot_heater_tune_verify_mixin_service as verify_service,
)
from portable_dropbot_controller.services import (
    portable_dropbot_temp_mixin_service as temp_service,
)
from portable_dropbot_controller.tests.test_heater_tune import (
    _Base,
    _Board,
    _Clock,
    _Recorder,
    _Sig,
    _Uart,
    _wait_until,
)

# --------------------------------------------------------------------- #
# A regulated loop on the fake signal board                              #
# --------------------------------------------------------------------- #


class _LoopSig(_Sig):
    """The fake heater plus TEMP_SET_TARGET and a regulated loop that
    closes a tenth of the gap to the target per read."""

    def __init__(self, target_ok=True, start_ok=True, **kwargs):
        super().__init__(**kwargs)
        self.target_c = None
        self.loop_on = False
        self.target_ok = target_ok
        self.start_ok = start_ok

    def temp_set_target(self, *, channel, target):
        self.calls.append(("target", channel, target))

        if self.target_ok:
            self.target_c = target

        return self.target_ok

    def temp_start_stop(self, *, channel, enable):
        if enable:
            self.calls.append(("start_stop", channel, 1))
            self.loop_on = self.start_ok

            return self.start_ok

        self.loop_on = self.loop_on and not self.off_ok

        return super().temp_start_stop(channel=channel, enable=0)

    def temp_read_info(self, channel):
        if not self.loop_on:
            return super().temp_read_info(channel)

        error_c = self.target_c - self.temp_c
        self.temp_c += error_c / 10.0

        return SimpleNamespace(
            current=round(self.temp_c, 2), output=min(100.0, max(0.0, 10 * error_c))
        )


class _LoopBoard(_Board):
    def set_target(self, channel, target_c):
        return self.sig.temp_set_target(channel=channel, target=target_c)

    def start(self, channel):
        return self.sig.temp_start_stop(channel=channel, enable=1)


def _verify(board, cancel=None, **config):
    config = {
        "channel": 0,
        "setpoint_c": 35.0,
        "max_temp_c": 50.0,
        "max_duration_s": 300.0,
        "hold_s": 5.0,
        **config,
    }

    return run_verify(
        board,
        VerifyConfig(**config),
        cancel or HeaterTuneCancel(),
        lambda run, current_c: None,
        clock=_Clock(),
        interval_s=0,
    )


def test_a_settled_verify_ends_off_and_reports_its_metrics():
    sig = _LoopSig()
    # Held past the metrics' 30 s steady-state tail, so it covers no rise.
    run, off_confirmed = _verify(_LoopBoard(sig), hold_s=40.0)

    assert run.phase == "done" and "settled" in run.reason
    assert off_confirmed and not sig.loop_on
    assert sig.calls[:2] == [("target", 0, 35.0), ("start_stop", 0, 1)]
    assert sig.calls[-1] == ("start_stop", 0, 0)

    done = HeaterTuneVerifyDone.model_validate(summarize_verify(run))

    assert done.ok and done.setpoint_c == 35.0
    assert done.metrics.settled
    assert done.metrics.overshoot_pct == pytest.approx(0.0)


@pytest.mark.parametrize(
    "sig_options, reason, sent",
    [
        ({"target_ok": False}, "set point refused", [("target", 0, 35.0)]),
        (
            {"start_ok": False},
            "loop start refused",
            [("target", 0, 35.0), ("start_stop", 0, 1)],
        ),
    ],
)
def test_a_refused_start_aborts_with_the_heater_off(sig_options, reason, sent):
    sig = _LoopSig(**sig_options)
    run, off_confirmed = _verify(_LoopBoard(sig))

    assert run.phase == "aborted" and run.reason == reason
    assert off_confirmed
    assert sig.calls == sent + [("start_stop", 0, 0)]
    assert summarize_verify(run)["ok"] is False


class _CancellingBoard(_LoopBoard):
    def __init__(self, sig, cancel, after_reads):
        super().__init__(sig)
        self.cancel = cancel
        self.reads_left = after_reads

    def read(self, channel):
        self.reads_left -= 1

        if self.reads_left == 0:
            self.cancel.cancel("cancelled by the operator")

        return super().read(channel)


def test_a_cancelled_verify_switches_the_heater_off_and_keeps_its_metrics():
    sig = _LoopSig()
    cancel = HeaterTuneCancel()
    run, off_confirmed = _verify(_CancellingBoard(sig, cancel, 8), cancel)

    done = HeaterTuneVerifyDone.model_validate(summarize_verify(run))

    assert off_confirmed and not sig.loop_on
    assert not done.ok and done.reason == "cancelled by the operator"
    assert done.metrics is not None


class _VanishingBoard(_LoopBoard):
    def read(self, channel):
        self.linked = False

        return super().read(channel)


def test_a_lost_link_leaves_the_heater_to_the_failsafe():
    sig = _LoopSig()
    run, off_confirmed = _verify(_VanishingBoard(sig))

    assert run.reason == CONNECTION_LOST_REASON
    assert not off_confirmed
    assert sig.calls == [("target", 0, 35.0), ("start_stop", 0, 1)]


# --------------------------------------------------------------------- #
# The verify mixin, composed with the tune and temp mixins               #
# --------------------------------------------------------------------- #


class _Harness(
    tune_service.PortableDropbotHeaterTuneMixinService,
    verify_service.PortableDropbotHeaterTuneVerifyMixinService,
    temp_service.PortableDropbotTempMixinService,
    _Base,
):
    pass


@pytest.fixture
def published(monkeypatch):
    recorders = {
        "done": _Recorder(HeaterTuneDone),
        "verify_done": _Recorder(HeaterTuneVerifyDone),
        "progress": _Recorder(HeaterTuneProgress),
    }
    monkeypatch.setattr(tune_service, "heater_tune_done_publisher", recorders["done"])
    monkeypatch.setattr(
        verify_service, "heater_tune_verify_done_publisher", recorders["verify_done"]
    )
    monkeypatch.setattr(
        verify_service, "heater_tune_progress_publisher", recorders["progress"]
    )
    monkeypatch.setattr(
        verify_service,
        "run_verify",
        functools.partial(run_verify, clock=_Clock(), interval_s=0.01),
    )

    return {name: recorder.published for name, recorder in recorders.items()}


@pytest.fixture
def harness():
    h = _Harness()
    h.proxy = SimpleNamespace(sig=_LoopSig(), uart=_Uart())

    yield h

    h.cleanup()


VERIFY = {"channel": 0, "setpoint_c": 35.0, "max_temp_c": 50.0, "hold_s": 600}


def _start_regulating(harness, published):
    harness.on_heater_tune_verify_start_request(json.dumps(VERIFY))
    _wait_until(lambda: published["progress"], timeout=10.0)


@pytest.mark.parametrize(
    "setup, change, expected",
    [
        (lambda h: setattr(h.proxy.sig, "temp_onoff", 0b10), {}, "ch1 is on"),
        (lambda h: None, {"setpoint_c": 25.5}, "nothing to verify"),
        (lambda h: None, {"setpoint_c": 49.0}, "above the cap minus the margin"),
        (lambda h: setattr(h.proxy, "uart", _Uart(max_temp_c=55)), {}, "below 50"),
    ],
)
def test_verify_is_refused_outside_the_vendor_rules(
    harness, published, setup, change, expected
):
    setup(harness)

    harness.on_heater_tune_verify_start_request(json.dumps({**VERIFY, **change}))

    [done] = published["verify_done"]

    assert not done.ok and expected in done.reason
    assert harness._heater_tune_thread is None
    assert all(call[0] != "target" for call in harness.proxy.sig.calls)


def test_a_refused_verify_request_is_answered(harness, published):
    harness._on_request_refused(
        HEATER_TUNE_VERIFY_START, json.dumps(VERIFY), "self-test run owns it"
    )

    assert published["verify_done"][0].reason == "self-test run owns it"


def test_a_running_verify_owns_the_heaters_and_blocks_a_tune(harness, published):
    _start_regulating(harness, published)

    assert harness._exclusive_owner_reason(TEMP_SET_TARGET)

    harness.on_heater_tune_start_request(
        json.dumps({"channel": 0, "duty_pct": 20, "max_temp_c": 50.0})
    )

    assert "already running" in published["done"][0].reason


def test_cancel_ends_a_verify_with_the_heater_off(harness, published):
    _start_regulating(harness, published)

    harness.on_heater_tune_cancel_request("")
    harness._heater_tune_thread.join(timeout=5)

    [done] = published["verify_done"]

    assert harness.proxy.sig.calls[-1] == ("start_stop", 0, 0)
    assert not harness.proxy.sig.loop_on
    assert done.reason == "cancelled by the operator" and done.off_confirmed
    assert harness._heater_tune_cancel is None

    progress = published["progress"][0]

    assert progress.phase == HEATER_TUNE_VERIFY_PHASE and progress.setpoint_c == 35.0
