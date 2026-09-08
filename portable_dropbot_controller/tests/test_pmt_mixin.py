# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Behaviour of the PMT capture routine against a scripted session: call
order, guaranteed teardown, CSV output, and the done/progress payloads.
The mixin is composed onto a stub base that stands in for the controller
base's proxy helpers. No Redis: the validated publishers are patched."""

# Standard library imports.
import struct

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.consts import PMT_STREAM_AVG, PMT_STREAM_OSR
from portable_dropbot_controller.services import (
    portable_dropbot_pmt_mixin_service as mod,
)
from portable_dropbot_controller.services.portable_dropbot_pmt_mixin_service import (
    PortableDropbotPmtMixinService,
)


def _frame(idx, values):
    return struct.pack("<HH", idx, len(values)) + struct.pack(
        f"<{len(values)}H", *values
    )


class _Uart:
    def __init__(self, log):
        self.log = log
        self.subscribers = {}

    def subscribe(self, cmd, callback):
        self.subscribers[cmd] = callback

    def unsubscribe(self, cmd):
        self.subscribers.pop(cmd, None)

    def setLEDIntensity(self, raw, fluorescence=True):
        self.log.append(f"led {raw}")
        return True

    def read_uid(self):
        return "abc123"

    def getBoardParameter(self, board, name):
        return b"_dp_pmt\x00" + struct.pack(">5i", 1000, 0, 24500, 0, 0)


class _Sig:
    def __init__(self, log, uart, stream_start_reply=object()):
        self.log = log
        self.uart = uart
        self.stream_start_reply = stream_start_reply

    def pmt_power(self, enable):
        self.log.append(f"power {enable}")
        return object()

    def pmt_gain_set(self, gain):
        self.log.append(f"gain {gain}")
        return True

    def pmt_stream(self, onoff, avg, osr):
        self.log.append(f"stream {onoff} {avg} {osr}")
        if onoff:
            # Deliver two frames the way the RX thread would, then reply.
            cb = self.uart.subscribers.get(0x123F)
            if cb is not None:
                cb(0x123F, _frame(0, [10, 20]))
                cb(0x123F, _frame(1, [30, 40]))
            return self.stream_start_reply
        return object()


class _Motor:
    def __init__(self, log):
        self.log = log

    def pmt_ctrl(self, slot):
        self.log.append(f"move {slot}")
        return object()

    def read_uid(self):
        return None


class _Session:
    def __init__(self, log, stream_start_reply=object()):
        self.uart = _Uart(log)
        self.sig = _Sig(log, self.uart, stream_start_reply)
        self.motor = _Motor(log)


class _Base(HasTraits):
    proxy = Any()
    _proxy_lock = Any()
    errors = List()
    log = List()

    def _proxy_call(self, context, call):
        return True, call()

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")

    def _apply_light_intensity(self):
        self.log.append("light restored")


class _Harness(PortableDropbotPmtMixinService, _Base):
    pass


@pytest.fixture
def published(monkeypatch, tmp_path):
    out = {"progress": [], "done": [], "spots": [], "pmt": []}
    monkeypatch.setattr(
        mod.pmt_capture_progress_publisher,
        "publish",
        lambda p, **k: out["progress"].append(p),
    )
    monkeypatch.setattr(
        mod.pmt_capture_done_publisher, "publish", lambda p, **k: out["done"].append(p)
    )
    monkeypatch.setattr(
        mod.pmt_spots_updated_publisher,
        "publish",
        lambda p, **k: out["spots"].append(p),
    )
    monkeypatch.setattr(
        mod,
        "publish_message",
        lambda topic, message: out["pmt"].append((topic, message)),
    )
    monkeypatch.setattr(mod, "get_current_experiment_directory", lambda: tmp_path)
    return out


def _request(entries):
    import json

    return json.dumps({"entries": entries})


def test_spots_read_publishes_non_zero_slots(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_spots_read_request("")
    assert published["spots"] == [
        {"spots": [{"slot": 1, "position_um": 1000}, {"slot": 3, "position_um": 24500}]}
    ]
    assert h._pmt_spot_positions == {1: 1000, 3: 24500}


def test_capture_runs_each_spot_and_tears_down(published, tmp_path):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_capture_request(
        _request(
            [
                {"slot": 3, "gain": 100, "exposure_s": 0.1},
                {"slot": 1, "gain": 50, "exposure_s": 0.1},
            ]
        )
    )
    assert h.log == [
        "led 0",
        "power 1",
        "move 3",
        "gain 100",
        f"stream 1 {PMT_STREAM_AVG} {PMT_STREAM_OSR}",
        "stream 0 0 0",
        "move 1",
        "gain 50",
        f"stream 1 {PMT_STREAM_AVG} {PMT_STREAM_OSR}",
        "stream 0 0 0",
        "stream 0 0 0",
        "power 0",
        "light restored",
    ]
    done = published["done"][-1]
    assert done["ok"] is True and done["aborted"] is False and done["error"] == ""
    assert [r["slot"] for r in done["results"]] == [3, 1]
    assert all(r["n_samples"] == 4 and r["csv_path"] for r in done["results"])
    assert sorted(p.name for p in (tmp_path / "captures" / "pmt").iterdir()) == sorted(
        r["csv_path"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for r in done["results"]
    )
    stages = [(p["slot"], p["stage"]) for p in published["progress"]]
    assert stages == [
        (3, "move"),
        (3, "gain"),
        (3, "stream"),
        (3, "saved"),
        (1, "move"),
        (1, "gain"),
        (1, "stream"),
        (1, "saved"),
    ]
    assert h.proxy.uart.subscribers == {}
    assert h._pmt_capturing is False


def test_failed_stream_start_records_error_and_continues(published):
    h = _Harness()
    h.proxy = _Session(h.log, stream_start_reply=None)
    h.on_pmt_capture_request(_request([{"slot": 2, "gain": 10, "exposure_s": 0.1}]))
    done = published["done"][-1]
    assert done["ok"] is False
    assert done["results"][0]["csv_path"] == ""
    assert "stream start" in done["results"][0]["error"]
    assert h.log[-3:] == ["stream 0 0 0", "power 0", "light restored"]
    assert published["progress"][-1]["stage"] == "failed"


def test_second_request_while_running_is_refused(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_capturing = True
    h.on_pmt_capture_request(_request([{"slot": 1, "gain": 10, "exposure_s": 0.1}]))
    assert published["done"] == [
        {
            "ok": False,
            "aborted": False,
            "directory": "",
            "results": [],
            "error": "a PMT capture is already running",
        }
    ]
    assert h.log == []


def test_empty_request_is_refused(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_capture_request(_request([]))
    assert published["done"][-1]["error"] == "no spots ticked"


def test_abort_stops_after_current_spot(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    original = h.proxy.sig.pmt_stream

    def stream_and_abort(onoff, avg, osr):
        reply = original(onoff, avg, osr)
        if onoff:
            h.on_pmt_capture_abort_request("")
        return reply

    h.proxy.sig.pmt_stream = stream_and_abort
    h.on_pmt_capture_request(
        _request(
            [
                {"slot": 1, "gain": 10, "exposure_s": 5.0},
                {"slot": 2, "gain": 10, "exposure_s": 5.0},
            ]
        )
    )
    done = published["done"][-1]
    assert done["aborted"] is True
    assert [r["slot"] for r in done["results"]] == [1]
    assert "move 2" not in h.log
    assert h.log[-2:] == ["power 0", "light restored"]
