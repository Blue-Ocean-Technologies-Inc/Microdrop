# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater auto-tune: the capture loop always leaves the heater off (cancel,
refused drive, unacknowledged OFF, exceptions, a lost link), the mixin
refuses to start or apply outside the vendor's rules, owns the heaters
while it runs, and an apply is held to what the firmware accepts. A fake
signal board and recording publishers; hardware-free, no Redis."""

# Standard library imports.
import functools
import json
import threading
import time
from types import SimpleNamespace

# Third-party imports.
import pytest
from dropbot_portable.heater_tune import CaptureConfig

# Enthought library imports.
from traits.api import Any, Bool, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DISCONNECT,
    HEATER_TUNE_OFF_ATTEMPTS,
    HEATER_TUNE_STYLES,
    PROTOCOL_SET_TEMPERATURE,
    TEMP_READ_INFO,
    TEMP_SET_TARGET,
    AlarmRaised,
    HeaterTuneApplied,
    HeaterTuneDone,
    HeaterTuneProgress,
    TemperatureReached,
)
from portable_dropbot_controller.heater_tune_capture import (
    CONNECTION_LOST_REASON,
    HeaterTuneCancel,
    run_step_capture,
    summarize_capture,
)
from portable_dropbot_controller.services import (
    portable_dropbot_heater_tune_mixin_service as tune_service,
)
from portable_dropbot_controller.services import (
    portable_dropbot_temp_mixin_service as temp_service,
)
from portable_dropbot_self_tests.consts import SELF_TEST_RUN

# --------------------------------------------------------------------- #
# A first-order heater and the board around it                           #
# --------------------------------------------------------------------- #


class _Sig:
    """The signal board's heater commands over a first-order plant (gain
    0.5 °C/%, tau 40 s, 1 s per read)."""

    def __init__(self, temp_onoff=0, drive_ok=True, off_ok=True):
        self.temp_c = 25.0
        self.duty = 0
        self.temp_onoff = temp_onoff
        self.drive_ok = drive_ok
        self.off_ok = off_ok
        self.calls = []

    def status(self):
        return SimpleNamespace(temp_onoff=self.temp_onoff)

    def temp_read_info(self, channel):
        self.temp_c += (25.0 + 0.5 * self.duty - self.temp_c) / 40.0

        return SimpleNamespace(current=round(self.temp_c, 2), output=self.duty)

    def temp_heat_pwm(self, duty1, duty2):
        self.calls.append(("pwm", duty1, duty2))

        if self.drive_ok:
            self.duty = max(duty1, duty2)

        return self.drive_ok

    def temp_start_stop(self, *, channel, enable):
        self.calls.append(("start_stop", channel, enable))

        if self.off_ok:
            self.duty = 0

        return self.off_ok


class _Board:
    """The HeaterTuneBoard methods straight on a _Sig."""

    def __init__(self, sig):
        self.sig = sig
        self.linked = True

    def attached(self):
        return self.linked

    def read(self, channel):
        info = self.sig.temp_read_info(channel)

        return info.current, info.output

    def drive(self, channel, duty_pct):
        return self.sig.temp_heat_pwm(duty_pct, 0)

    def off(self, channel):
        return self.sig.temp_start_stop(channel=channel, enable=0)


class _Clock:
    """One second per call: one reading a second, as the real loop."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 1.0

        return self.now


def _capture(board, cancel=None, **config):
    config = {"channel": 0, "duty_pct": 20, "max_duration_s": 60.0, **config}

    return run_step_capture(
        board,
        CaptureConfig(**config),
        cancel or HeaterTuneCancel(),
        lambda capture, current_c: None,
        clock=_Clock(),
        interval_s=0,
    )


def test_a_full_capture_ends_off_and_proposes_gains_per_style():
    sig = _Sig()
    capture, off_confirmed = _capture(_Board(sig))

    assert capture.phase == "done"
    assert off_confirmed and sig.duty == 0
    assert sig.calls[0] == ("pwm", 20, 0)
    assert sig.calls[-1] == ("start_stop", 0, 0)

    done = HeaterTuneDone.model_validate(summarize_capture(capture))

    assert done.ok
    assert set(done.proposals) == set(HEATER_TUNE_STYLES)
    assert all(0 < p.kp <= 100 and 0 < p.ki <= 100 for p in done.proposals.values())
    assert done.fit.gain == pytest.approx(0.5, rel=0.3)


class _CancellingBoard(_Board):
    def __init__(self, sig, cancel, after_reads):
        super().__init__(sig)
        self.cancel = cancel
        self.reads_left = after_reads

    def read(self, channel):
        self.reads_left -= 1

        if self.reads_left == 0:
            self.cancel.cancel("cancelled by the operator")

        return super().read(channel)


def test_a_cancel_while_heating_switches_the_heater_off():
    sig = _Sig()
    cancel = HeaterTuneCancel()
    capture, off_confirmed = _capture(_CancellingBoard(sig, cancel, 20), cancel)

    assert capture.phase == "aborted"
    assert capture.reason == "cancelled by the operator"
    assert off_confirmed and sig.duty == 0
    assert sig.calls[-1] == ("start_stop", 0, 0)
    assert summarize_capture(capture)["ok"] is False


def test_a_refused_drive_aborts_with_the_heater_off():
    sig = _Sig(drive_ok=False)
    capture, off_confirmed = _capture(_Board(sig))

    assert capture.reason == "drive refused"
    assert off_confirmed
    assert sig.calls[-1] == ("start_stop", 0, 0)


def test_an_unacknowledged_off_is_retried_then_reported():
    sig = _Sig(off_ok=False)
    cancel = HeaterTuneCancel()
    _capture_result, off_confirmed = _capture(_CancellingBoard(sig, cancel, 20), cancel)
    offs = [call for call in sig.calls if call[0] == "start_stop"]

    assert not off_confirmed
    # The abort's OFF attempts, then the final teardown's.
    assert len(offs) == 2 * HEATER_TUNE_OFF_ATTEMPTS


class _FailingBoard(_Board):
    def read(self, channel):
        if self.sig.duty:
            raise RuntimeError("transport broke")

        return super().read(channel)


def test_an_exception_while_heating_still_switches_the_heater_off():
    sig = _Sig()

    with pytest.raises(RuntimeError):
        _capture(_FailingBoard(sig))

    assert sig.calls[-1] == ("start_stop", 0, 0)
    assert sig.duty == 0


class _VanishingBoard(_Board):
    def read(self, channel):
        if self.sig.duty:
            self.linked = False

        return super().read(channel)


def test_a_lost_link_sends_nothing_and_leaves_it_to_the_failsafe():
    sig = _Sig()
    capture, off_confirmed = _capture(_VanishingBoard(sig))

    assert capture.reason == CONNECTION_LOST_REASON
    assert not off_confirmed
    assert sig.calls == [("pwm", 20, 0)]


# --------------------------------------------------------------------- #
# The mixin: start / apply rules, heater ownership, teardown             #
# --------------------------------------------------------------------- #


class _Recorder:
    def __init__(self, validator_class):
        self.validator_class = validator_class
        self.published = []

    def publish(self, payload):
        self.published.append(self.validator_class.model_validate(payload))


class _Uart:
    def __init__(self, max_temp_c=120):
        self.max_temp_c = max_temp_c

    def heater_failsafe(self):
        return 300, 5, self.max_temp_c


class _Base(HasTraits):
    proxy = Any()
    portable_dropbot_connection_active = Bool(True)

    def _proxy_call(self, context, call, serialize=True):
        if self.proxy is None:
            return False, None

        try:
            return True, call()
        except Exception as error:
            return False, error

    def _publish_error(self, context, error):
        pass

    def _exclusive_owner_reason(self, topic):
        return ""

    def _on_request_refused(self, topic, message, reason):
        pass

    def _on_motor_estop(self):
        pass

    def cleanup(self):
        pass


class _Harness(
    tune_service.PortableDropbotHeaterTuneMixinService,
    temp_service.PortableDropbotTempMixinService,
    _Base,
):
    pass


@pytest.fixture
def published(monkeypatch):
    recorders = {
        "done": _Recorder(HeaterTuneDone),
        "progress": _Recorder(HeaterTuneProgress),
        "applied": _Recorder(HeaterTuneApplied),
        "reached": _Recorder(TemperatureReached),
    }
    monkeypatch.setattr(tune_service, "heater_tune_done_publisher", recorders["done"])
    monkeypatch.setattr(
        tune_service, "heater_tune_progress_publisher", recorders["progress"]
    )
    monkeypatch.setattr(
        tune_service, "heater_tune_applied_publisher", recorders["applied"]
    )
    monkeypatch.setattr(
        tune_service, "temperature_reached_publisher", recorders["reached"]
    )
    # A fast loop on a one-second-per-read clock: the real one reads once
    # a second, and the baseline alone lasts 10 s.
    monkeypatch.setattr(
        tune_service,
        "run_step_capture",
        functools.partial(run_step_capture, clock=_Clock(), interval_s=0.01),
    )

    return {name: recorder.published for name, recorder in recorders.items()}


@pytest.fixture
def harness():
    h = _Harness()
    h.proxy = SimpleNamespace(sig=_Sig(), uart=_Uart())

    yield h

    h.cleanup()


START = {"channel": 0, "duty_pct": 20, "max_temp_c": 50.0, "max_duration_s": 600}


def _wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout

    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _start_heating(harness):
    harness.on_heater_tune_start_request(json.dumps(START))
    _wait_until(lambda: harness.proxy.sig.duty > 0, timeout=20.0)


@pytest.mark.parametrize(
    "setup, expected",
    [
        (lambda h: setattr(h.proxy.sig, "temp_onoff", 0b10), "ch1 is on"),
        (
            lambda h: setattr(h, "_temp_reached_cancel", threading.Event()),
            "protocol step",
        ),
        (lambda h: setattr(h.proxy, "uart", _Uart(max_temp_c=55)), "below 50"),
    ],
)
def test_start_is_refused_outside_the_vendor_rules(harness, published, setup, expected):
    setup(harness)

    harness.on_heater_tune_start_request(json.dumps(START))

    [done] = published["done"]

    assert not done.ok and expected in done.reason
    assert harness._heater_tune_thread is None
    assert harness.proxy.sig.calls == []


def test_an_invalid_start_is_answered_not_run(harness, published):
    harness.on_heater_tune_start_request(json.dumps({**START, "duty_pct": 0}))

    assert published["done"][0].ok is False
    assert harness.proxy.sig.calls == []


def test_a_running_tune_owns_the_heaters(harness, published):
    _start_heating(harness)

    assert harness._exclusive_owner_reason(TEMP_SET_TARGET)
    assert harness._exclusive_owner_reason(SELF_TEST_RUN)
    assert harness._exclusive_owner_reason(TEMP_READ_INFO) == ""

    step = json.dumps({"channel": 0, "target_c": 40.0, "tolerance_c": 1.0})
    harness._on_request_refused(PROTOCOL_SET_TEMPERATURE, step, "tune owns it")

    assert published["reached"][0].error == "tune owns it"

    harness._on_request_refused(DISCONNECT, "", "tune owns it")
    harness._heater_tune_thread.join(timeout=5)

    assert harness.proxy.sig.duty == 0
    assert published["done"][-1].reason == "disconnect requested"


def test_cancel_switches_the_heater_off_and_releases_the_claim(harness, published):
    _start_heating(harness)

    harness.on_heater_tune_cancel_request("")
    harness._heater_tune_thread.join(timeout=5)

    [done] = published["done"]

    assert harness.proxy.sig.calls[-1] == ("start_stop", 0, 0)
    assert harness.proxy.sig.duty == 0
    assert done.reason == "cancelled by the operator" and done.off_confirmed
    assert harness._heater_tune_cancel is None
    assert published["progress"][0].phase == "baseline"


def _alarm(detail):
    return AlarmRaised(
        command="0x12FF",
        reports=[
            {
                "text": "[09001] Heater over temperature",
                "code": "09001",
                "detail": detail,
                "active": 1,
            }
        ],
    ).model_dump_json()


def test_a_failsafe_alarm_on_the_tuned_heater_ends_the_tune(harness, published):
    _start_heating(harness)

    harness.on_alarm_signal(_alarm("htr1 S1 above max"))

    assert not harness._heater_tune_cancel.is_set()

    harness.on_alarm_signal(_alarm("htr0 S1 above max"))
    harness._heater_tune_thread.join(timeout=5)

    assert "09001" in published["done"][-1].reason
    assert harness.proxy.sig.duty == 0


def test_a_disconnect_ends_the_tune(harness, published):
    _start_heating(harness)

    harness.proxy = None
    harness.portable_dropbot_connection_active = False
    harness._heater_tune_thread.join(timeout=5)

    [done] = published["done"]

    assert done.reason == CONNECTION_LOST_REASON
    assert not done.off_confirmed


APPLY = {
    "channel": 1,
    "kp": 4.5,
    "ki": 0.11,
    "kd": 0.0,
    "smith_model": [0.5, 40.0, 2.0],
}


@pytest.fixture
def applied_calls(monkeypatch):
    calls = []

    def apply_tuning(sig, uart, channel, tuning, model_row, persist, period_ms):
        calls.append((channel, tuning.kp, tuning.ki, model_row, persist, period_ms))

        return {"gains": True, "smith": "ok", "gains_persisted": None}

    monkeypatch.setattr(tune_service, "apply_tuning", apply_tuning)

    return calls


def test_a_valid_apply_writes_gains_and_model(harness, published, applied_calls):
    harness.on_heater_tune_apply_request(json.dumps(APPLY))

    assert applied_calls == [(1, 4.5, 0.11, (0.5, 40.0, 2.0), False, 1000)]
    assert published["applied"][0].gains and published["applied"][0].smith == "ok"


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"kp": 0.0, "ki": 0.0}, "Kp and Ki cannot both be 0"),
        ({"kp": 101.0}, "less than or equal to 100"),
        ({"smith_model": [0.5, 900.0, 2.0]}, "time constant"),
        ({"smith_model": [0.0, 40.0, 2.0]}, "model gain"),
    ],
)
def test_an_apply_outside_the_firmware_limits_is_refused(
    harness, published, applied_calls, change, expected
):
    harness.on_heater_tune_apply_request(json.dumps({**APPLY, **change}))

    assert applied_calls == []
    assert expected in published["applied"][0].error


def test_an_apply_while_a_heater_is_on_is_refused(harness, published, applied_calls):
    harness.proxy.sig.temp_onoff = 0b01

    harness.on_heater_tune_apply_request(json.dumps(APPLY))

    assert applied_calls == []
    assert "ch0 is on" in published["applied"][0].error
