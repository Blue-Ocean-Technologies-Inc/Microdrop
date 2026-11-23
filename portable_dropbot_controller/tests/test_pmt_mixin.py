# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Behaviour of the three PMT sessions (capture, live stream, buffered
acquire) against a scripted session: call order, the shared claim's
refusals, guaranteed teardown, CSV output, and the done/progress/updated
payloads. The mixin is composed onto a stub base that stands in for the
controller base's proxy helpers. No Redis: the validated publishers are
patched, but the payloads they receive are still round-tripped through
the pydantic models, so a renamed or missing field fails here too."""

# Standard library imports.
import json
import struct
import threading
import time
from collections import namedtuple
from pathlib import Path

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, HasTraits, Int, List

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    MECHANISM_STATE_FAULT,
    MOTOR_ACTION_PARK,
    MOTOR_IDS,
    PMT_ADC_FULL_SCALE,
    PMT_LEGACY_PARK_LOCATION,
    PMT_LOCATION_MOVING,
    PMT_PRESET_PARK_MOTOR_FIRMWARE,
    PMT_RF_OHMS,
    PMT_SPOT_SLOTS,
    PMT_STREAM_AVG,
    PMT_STREAM_DATA_CMD,
    PMT_STREAM_OSR,
    PmtAcquireDone,
    PmtAdcUpdated,
    PmtCaptureDone,
    PmtCaptureProgress,
    PmtSpotsUpdated,
    PmtStreamUpdated,
)
from portable_dropbot_controller.services import (
    portable_dropbot_pmt_mixin_service as mod,
)
from portable_dropbot_controller.services.portable_dropbot_pmt_mixin_service import (
    PortableDropbotPmtMixinService,
)

#: The generated motor proxy's PMT_CTRL / MOTOR_CONTROL replies.
_PmtCtrlReply = namedtuple("_PmtCtrlReply", "location")
_MotorControlReply = namedtuple("_MotorControlReply", "motor_id status position")
#: Motor firmware older than the preset/park change.
_LEGACY_MOTOR_FIRMWARE = (1, 0, 0, 24)


class _LastResult:
    """The driver's CommandResult for a refused request."""

    def describe(self):
        return "BUSY: the board refused the command"


def _frame(idx, values):
    return struct.pack("<HH", idx, len(values)) + struct.pack(
        f"<{len(values)}H", *values
    )


class _PmtCapture:
    """Stand-in for the driver's PmtCapture: the fields the buffered
    acquire reads (samples/n_received/n_expected/missing/aborted/busy/
    error/complete)."""

    def __init__(
        self,
        samples,
        n_expected=None,
        missing=None,
        aborted=False,
        busy=False,
        error=None,
    ):
        self.samples = samples
        self.n_received = len(samples)
        self.n_expected = n_expected if n_expected is not None else len(samples)
        self.missing = missing or []
        self.aborted = aborted
        self.busy = busy
        self.error = error

    @property
    def complete(self):
        return (
            self.error is None
            and not self.aborted
            and self.n_expected > 0
            and self.n_received >= self.n_expected
        )


class _AdcDiagReply:
    def __init__(self, adc_type):
        self.adc_type = adc_type


class _Uart:
    def __init__(self, log):
        self.log = log
        self.subscribers = {}
        #: What the buffered acquire's collector returns; tests override
        #: this per case.
        self.acquire_capture = _PmtCapture([100, 200, 300])

    def subscribe(self, cmd, callback):
        self.subscribers[cmd] = callback

    def unsubscribe(self, cmd):
        self.subscribers.pop(cmd, None)

    def setLEDIntensity(self, raw, fluorescence=True):
        self.log.append(f"led {raw}")
        return True

    def read_uid(self):
        return "abc123"

    #: The motor board's PMT position table (pmt_defaults), location 1 first.
    pmt_locations = (0, 1000, 0, 24500, 0, 0)
    #: The PMT entry of _dp_park: (source, value_um); None answers no reply.
    pmt_park = (0, 0)

    def getBoardParameter(self, board, name):
        self.log.append(f"read {name}")

        if name == "park":
            if self.pmt_park is None:
                return None

            entries = [(0, 0)] * PMT_SPOT_SLOTS
            entries[MOTOR_IDS["pmt"]] = self.pmt_park

            return b"_dp_park\x00" + struct.pack(
                ">12i", *(value for entry in entries for value in entry)
            )

        return b"_dp_pmt\x00" + struct.pack(">6i", *self.pmt_locations)

    def pmt_acquire_collect(self):
        self.log.append("acquire_collect")
        return self.acquire_capture

    def last_result(self, cmd=None):
        return _LastResult()


class _Sig:
    def __init__(
        self, log, uart, stream_start_reply=object(), fail_starts=0, adc_type=2
    ):
        self.log = log
        self.uart = uart
        self.stream_start_reply = stream_start_reply
        #: Number of upcoming stream-start calls that answer with no
        #: reply before returning `stream_start_reply` as normal.
        self.fail_starts = fail_starts
        #: spi_adc_diag's reply code; 2 = ADS7076 (the assumed default).
        self.adc_type = adc_type

    def spi_adc_diag(self):
        self.log.append("adc_diag")
        return _AdcDiagReply(self.adc_type)

    def pmt_power(self, enable):
        self.log.append(f"power {enable}")
        return object()

    def pmt_gain_set(self, gain):
        self.log.append(f"gain {gain}")
        return True

    def pmt_stream(self, onoff, avg, osr):
        self.log.append(f"stream {onoff} {avg} {osr}")
        if onoff:
            if self.fail_starts > 0:
                self.fail_starts -= 1
                return None
            # Deliver two frames the way the RX thread would, then reply.
            cb = self.uart.subscribers.get(PMT_STREAM_DATA_CMD)
            if cb is not None:
                cb(PMT_STREAM_DATA_CMD, _frame(0, [10, 20]))
                cb(PMT_STREAM_DATA_CMD, _frame(1, [30, 40]))
            return self.stream_start_reply
        return object()


class _Motor:
    def __init__(self, log):
        self.log = log
        #: PMT_CTRL's reply location; None answers no reply (a BUSY), and
        #: the default lands on the requested location.
        self.pmt_location = "landed"
        self.park_status = 0

    def pmt_ctrl(self, location):
        self.log.append(f"move {location}")

        if self.pmt_location is None:
            return None

        landed = location if self.pmt_location == "landed" else self.pmt_location

        return _PmtCtrlReply(landed)

    def motor_control(self, motor_id, action, distance):
        self.log.append(f"motor_control {motor_id} {action} {distance}")

        return _MotorControlReply(motor_id, self.park_status, 0)

    def read_uid(self):
        return None


class _Session:
    def __init__(self, log, stream_start_reply=object(), fail_starts=0, adc_type=2):
        self.uart = _Uart(log)
        self.sig = _Sig(log, self.uart, stream_start_reply, fail_starts, adc_type)
        self.motor = _Motor(log)


class _Base(HasTraits):
    proxy = Any()
    _proxy_lock = Any()
    errors = List()
    log = List()
    #: The motor firmware version; None is unknown, even after a re-read.
    motor_firmware = Any(_LEGACY_MOTOR_FIRMWARE)
    #: How many times the firmware version was asked for.
    firmware_queries = Int()
    #: The contexts of the driver calls made outside the proxy lock.
    unserialized = List()

    def _motor_firmware_known(self):
        self.firmware_queries += 1

        return self.motor_firmware is not None

    def _motor_firmware_at_least(self, version):
        return self.motor_firmware is not None and self.motor_firmware >= version

    def _proxy_call(self, context, call, serialize=True):
        if not serialize:
            self.unserialized.append(context)

        return True, call()

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")

    def _apply_light_intensity(self):
        self.log.append("light restored")


class _Harness(PortableDropbotPmtMixinService, _Base):
    pass


@pytest.fixture
def published(monkeypatch, tmp_path):
    out = {
        "progress": [],
        "done": [],
        "spots": [],
        "pmt": [],
        "stream": [],
        "adc": [],
        "acquire": [],
    }
    monkeypatch.setattr(
        mod.pmt_capture_progress_publisher,
        "publish",
        lambda p, **k: out["progress"].append(
            PmtCaptureProgress.model_validate(p).model_dump()
        ),
    )
    monkeypatch.setattr(
        mod.pmt_capture_done_publisher,
        "publish",
        lambda p, **k: out["done"].append(
            PmtCaptureDone.model_validate(p).model_dump()
        ),
    )
    monkeypatch.setattr(
        mod.pmt_spots_updated_publisher,
        "publish",
        lambda p, **k: out["spots"].append(
            PmtSpotsUpdated.model_validate(p).model_dump()
        ),
    )
    monkeypatch.setattr(
        mod.pmt_stream_updated_publisher,
        "publish",
        lambda p, **k: out["stream"].append(
            PmtStreamUpdated.model_validate(p).model_dump()
        ),
    )
    monkeypatch.setattr(
        mod.pmt_adc_updated_publisher,
        "publish",
        lambda p, **k: out["adc"].append(PmtAdcUpdated.model_validate(p).model_dump()),
    )
    monkeypatch.setattr(
        mod.pmt_acquire_done_publisher,
        "publish",
        lambda p, **k: out["acquire"].append(
            PmtAcquireDone.model_validate(p).model_dump()
        ),
    )
    monkeypatch.setattr(
        mod,
        "publish_message",
        lambda topic, message: out["pmt"].append((topic, message)),
    )
    monkeypatch.setattr(mod, "get_current_experiment_directory", lambda: tmp_path)
    return out


def _request(entries):
    return json.dumps({"entries": entries})


def _run(h, message):
    """Call the handler, then join the capture thread it may have started
    (a refusal starts none — `_pmt_capture_thread` stays at its default
    `None`) so every assertion below still sees the routine's finished
    state, the way it did back when the routine ran inline."""
    h.on_pmt_capture_request(message)
    if h._pmt_capture_thread is not None:
        h._pmt_capture_thread.join(timeout=5)


@pytest.mark.parametrize(
    "motor_firmware, expected",
    [
        # Older firmware: location 1 is park, so location n + 1 is spot n.
        (_LEGACY_MOTOR_FIRMWARE, {1: 1000, 3: 24500}),
        # Preset firmware: location n is spot n.
        (PMT_PRESET_PARK_MOTOR_FIRMWARE, {2: 1000, 4: 24500}),
    ],
)
def test_spots_read_maps_locations_onto_spots(published, motor_firmware, expected):
    h = _Harness(motor_firmware=motor_firmware)
    h.proxy = _Session(h.log)

    h.on_pmt_spots_read_request("")

    assert published["spots"] == [
        {
            "spots": [
                {"slot": slot, "position_um": position}
                for slot, position in expected.items()
            ]
        }
    ]
    assert h._pmt_spot_positions == expected


@pytest.mark.parametrize(
    "motor_firmware, spot, location",
    [
        (_LEGACY_MOTOR_FIRMWARE, 2, 2 + PMT_LEGACY_PARK_LOCATION),
        (_LEGACY_MOTOR_FIRMWARE, 0, PMT_LEGACY_PARK_LOCATION),
        (PMT_PRESET_PARK_MOTOR_FIRMWARE, 1, 1),
        (PMT_PRESET_PARK_MOTOR_FIRMWARE, PMT_SPOT_SLOTS, PMT_SPOT_SLOTS),
    ],
)
def test_move_to_spot_moves_to_the_spots_location(
    published, motor_firmware, spot, location
):
    h = _Harness(motor_firmware=motor_firmware)
    h.proxy = _Session(h.log)

    h.on_pmt_move_to_spot_request(str(spot))

    assert h.log == [f"move {location}"]
    assert h.errors == []


def test_move_to_park_uses_the_motor_park_on_preset_firmware(published):
    h = _Harness(motor_firmware=PMT_PRESET_PARK_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)

    h.on_pmt_move_to_spot_request("0")

    assert h.log == [f"motor_control {MOTOR_IDS['pmt']} {MOTOR_ACTION_PARK} 0"]
    assert h.errors == []


@pytest.mark.parametrize(
    "motor_firmware, spot",
    [
        # Older firmware has one spot fewer: its location 1 is park.
        (_LEGACY_MOTOR_FIRMWARE, PMT_SPOT_SLOTS),
        (PMT_PRESET_PARK_MOTOR_FIRMWARE, PMT_SPOT_SLOTS + 1),
        (PMT_PRESET_PARK_MOTOR_FIRMWARE, -1),
    ],
)
def test_move_to_spot_refuses_a_spot_the_firmware_lacks(
    published, motor_firmware, spot
):
    h = _Harness(motor_firmware=motor_firmware)
    h.proxy = _Session(h.log)

    h.on_pmt_move_to_spot_request(str(spot))

    assert h.log == []
    assert len(h.errors) == 1 and f"spot {spot}" in h.errors[0]


def test_move_refused_busy_while_the_tray_moves_is_reported(published):
    h = _Harness(motor_firmware=PMT_PRESET_PARK_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)
    h.proxy.motor.pmt_location = None

    h.on_pmt_move_to_spot_request("3")

    assert h.log == ["move 3"]
    assert len(h.errors) == 1 and "BUSY" in h.errors[0]


@pytest.mark.parametrize(
    "location, reason",
    [(MECHANISM_STATE_FAULT, "FAULT"), (PMT_LOCATION_MOVING, "moving")],
)
def test_move_that_does_not_land_is_reported(published, location, reason):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.proxy.motor.pmt_location = location

    h.on_pmt_move_to_spot_request("1")

    assert len(h.errors) == 1 and reason in h.errors[0]


def test_park_refused_by_the_motor_is_reported(published):
    h = _Harness(motor_firmware=PMT_PRESET_PARK_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)
    h.proxy.motor.park_status = -7

    h.on_pmt_move_to_spot_request("0")

    assert len(h.errors) == 1 and "-7" in h.errors[0]


def test_move_to_spot_refused_while_a_capture_is_running(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_capturing = True

    h.on_pmt_move_to_spot_request("1")

    assert h.log == []


def test_capture_runs_each_spot_and_tears_down(published, tmp_path):
    h = _Harness()
    h.proxy = _Session(h.log)
    _run(
        h,
        _request(
            [
                {"slot": 3, "gain": 100, "exposure_s": 1.0},
                {"slot": 1, "gain": 50, "exposure_s": 1.0},
            ]
        ),
    )
    assert h.log == [
        "adc_diag",
        "led 0",
        "power 1",
        "move 4",
        "gain 100",
        f"stream 1 {PMT_STREAM_AVG} {PMT_STREAM_OSR}",
        "stream 0 0 0",
        "move 2",
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


@pytest.mark.parametrize(
    "motor_firmware, spot_move, park",
    [
        (_LEGACY_MOTOR_FIRMWARE, "move 2", f"move {PMT_LEGACY_PARK_LOCATION}"),
        (
            PMT_PRESET_PARK_MOTOR_FIRMWARE,
            "move 1",
            f"motor_control {MOTOR_IDS['pmt']} {MOTOR_ACTION_PARK} 0",
        ),
    ],
)
def test_capture_moves_and_parks_per_firmware(
    published, tmp_path, motor_firmware, spot_move, park
):
    h = _Harness(motor_firmware=motor_firmware)
    h.proxy = _Session(h.log)
    payload = json.loads(_request([{"slot": 1, "gain": 50, "exposure_s": 1.0}]))
    payload["park_motor"] = True

    _run(h, json.dumps(payload))

    assert spot_move in h.log
    assert h.log[-1] == park
    assert published["done"][-1]["ok"] is True

    # The CSV records the motor location the spot was measured at.
    csv_path = Path(published["done"][-1]["results"][0]["csv_path"])
    location = spot_move.split()[-1]

    assert f"# motor_location={location}" in csv_path.read_text().splitlines()


def test_capture_fails_a_spot_the_firmware_lacks_and_continues(published):
    h = _Harness(motor_firmware=_LEGACY_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)

    _run(
        h,
        _request(
            [
                {"slot": PMT_SPOT_SLOTS, "gain": 10, "exposure_s": 1.0},
                {"slot": 1, "gain": 20, "exposure_s": 1.0},
            ]
        ),
    )

    done = published["done"][-1]

    assert done["ok"] is False
    assert f"spot {PMT_SPOT_SLOTS}" in done["results"][0]["error"]
    assert done["results"][1]["error"] == ""
    assert "move 2" in h.log


def test_capture_spot_refused_busy_fails_that_spot(published):
    h = _Harness(motor_firmware=PMT_PRESET_PARK_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)
    h.proxy.motor.pmt_location = None

    _run(h, _request([{"slot": 2, "gain": 10, "exposure_s": 1.0}]))

    done = published["done"][-1]

    assert done["ok"] is False
    assert "BUSY" in done["results"][0]["error"]


def test_failed_stream_start_records_error_and_continues(published):
    h = _Harness()
    # Only the first stream start fails, so the second spot must still run.
    h.proxy = _Session(h.log, fail_starts=1)
    _run(
        h,
        _request(
            [
                {"slot": 2, "gain": 10, "exposure_s": 1.0},
                {"slot": 4, "gain": 20, "exposure_s": 1.0},
            ]
        ),
    )
    done = published["done"][-1]
    assert done["ok"] is False
    assert [r["slot"] for r in done["results"]] == [2, 4]
    assert done["results"][0]["csv_path"] == ""
    assert "stream start" in done["results"][0]["error"]
    assert done["results"][1]["csv_path"] != ""
    assert done["results"][1]["error"] == ""
    assert h.log[-3:] == ["stream 0 0 0", "power 0", "light restored"]
    stages = {
        p["slot"]: p["stage"]
        for p in published["progress"]
        if p["stage"] in ("failed", "saved")
    }
    assert stages == {2: "failed", 4: "saved"}


def test_second_request_while_running_is_refused(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_capturing = True
    h.on_pmt_capture_request(_request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    assert published["done"] == [
        {
            "ok": False,
            "aborted": False,
            "directory": "",
            "results": [],
            "adc_full_scale": PMT_ADC_FULL_SCALE,
            "rf_ohms": PMT_RF_OHMS,
            "request_id": "",
            "label": "",
            "error": "a PMT capture is running",
        }
    ]
    assert h.log == []


def test_capture_refused_while_streaming(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_streaming = True
    h.on_pmt_capture_request(_request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    assert published["done"][-1]["error"] == "the live stream is running"
    assert h.log == []


def test_capture_refused_while_acquiring(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_acquiring = True
    h.on_pmt_capture_request(_request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    assert published["done"][-1]["error"] == "a buffered acquire is running"
    assert h.log == []


def test_empty_request_is_refused(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_capture_request(_request([]))
    assert published["done"][-1]["error"] == "no spots ticked"


def test_malformed_request_still_publishes_a_done_refusal(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_capture_request("not json")
    done = published["done"][-1]
    assert done["ok"] is False
    assert done["error"] != ""
    # The error signal fires too; the done ack does not replace it.
    assert h.errors


def test_done_echoes_request_id_and_label_on_success(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    payload = json.loads(_request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    payload["request_id"] = "abc-123:end"
    payload["label"] = "step1.2-end"
    _run(h, json.dumps(payload))
    done = published["done"][-1]
    assert done["ok"] is True
    assert done["request_id"] == "abc-123:end"
    assert done["label"] == "step1.2-end"


def test_done_echoes_request_id_and_label_on_refusal(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_capturing = True
    payload = json.loads(_request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    payload["request_id"] = "xyz-456:start"
    payload["label"] = "step2-start"
    h.on_pmt_capture_request(json.dumps(payload))
    done = published["done"][-1]
    assert done["error"] == "a PMT capture is running"
    assert done["request_id"] == "xyz-456:start"
    assert done["label"] == "step2-start"


def test_capture_with_label_prefixes_csv_filename_and_meta(published, tmp_path):
    h = _Harness()
    h.proxy = _Session(h.log)
    payload = json.loads(_request([{"slot": 2, "gain": 30, "exposure_s": 1.0}]))
    payload["label"] = "step1.2-end"
    payload["request_id"] = "uuid123:end"
    _run(h, json.dumps(payload))
    done = published["done"][-1]
    csv_path = Path(done["results"][0]["csv_path"])
    assert csv_path.name.startswith("pmt_step1.2-end_spot2_")
    csv_lines = csv_path.read_text().splitlines()
    assert "# request_id=uuid123:end" in csv_lines
    assert "# label=step1.2-end" in csv_lines


def test_capture_with_no_proxy_still_acks_a_failed_done(published):
    h = _Harness()
    h.proxy = None
    _run(h, _request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    done = published["done"][-1]
    assert done["ok"] is False
    assert done["error"] != ""
    assert done["results"] == []
    assert h._pmt_capturing is False
    assert h._pmt_capture_abort is None


def test_read_board_uids_tolerates_a_reply_without_uid(published):
    h = _Harness()
    h.proxy = _Session(h.log)

    class _ReplyWithoutUid:
        pass

    h.proxy.motor.read_uid = lambda: _ReplyWithoutUid()
    uids = h._read_board_uids()
    assert uids == {"mcu_uid": "abc123", "motor_uid": "unavailable"}


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
    _run(
        h,
        _request(
            [
                {"slot": 1, "gain": 10, "exposure_s": 5.0},
                {"slot": 2, "gain": 10, "exposure_s": 5.0},
            ]
        ),
    )
    done = published["done"][-1]
    assert done["aborted"] is True
    assert [r["slot"] for r in done["results"]] == [1]
    assert "move 3" not in h.log
    assert h.log[-2:] == ["power 0", "light restored"]


def test_adc_query_stores_full_scale_and_feeds_capture_meta(published, tmp_path):
    h = _Harness()
    h.proxy = _Session(h.log, adc_type=1)  # ADC128S052, 4096 counts
    h.on_pmt_adc_query_request("")
    assert published["adc"] == [
        {"adc_type": 1, "name": "ADC128S052 (12-bit)", "full_scale": 4096, "error": ""}
    ]
    assert h._pmt_adc_full_scale == 4096

    # A subsequent capture's meta and done payload carry the queried scale.
    _run(h, _request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    done = published["done"][-1]
    assert done["adc_full_scale"] == 4096
    csv_text = Path(done["results"][0]["csv_path"]).read_text()
    assert "# adc_full_scale=4096" in csv_text.splitlines()


def test_adc_query_reports_unknown_type_with_zero_full_scale(published):
    h = _Harness()
    h.proxy = _Session(h.log, adc_type=3)
    h.on_pmt_adc_query_request("")
    assert published["adc"] == [
        {"adc_type": 3, "name": "unknown (3)", "full_scale": 0, "error": ""}
    ]
    # An unknown reading never overwrites the last known-good full scale.
    assert h._pmt_adc_full_scale == PMT_ADC_FULL_SCALE


def test_adc_query_refused_while_a_session_is_running(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_capturing = True
    h.on_pmt_adc_query_request("")
    assert published["adc"][-1] == {
        "adc_type": -1,
        "name": "",
        "full_scale": 0,
        "error": "a PMT capture is running",
    }
    assert h.log == []


def _wait_for_stream_batch(published, timeout=2.0):
    """Poll for the live-stream thread's first non-empty batch instead of
    sleeping a fixed amount; PMT_STREAM_PUBLISH_INTERVAL_S is patched down
    to keep this fast."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if any(p["samples"] for p in published["stream"]):
            return

        time.sleep(0.005)

    pytest.fail("no live-stream batch published in time")


def test_live_stream_batches_then_stop_tears_down(published, monkeypatch):
    monkeypatch.setattr(mod, "PMT_STREAM_PUBLISH_INTERVAL_S", 0.01)
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_stream_start_request(json.dumps({"gain": 77, "avg": 16, "osr": 6}))
    assert h._pmt_streaming is True

    # Wait for a batch before inspecting the list: the ack (published
    # before the while loop starts) is guaranteed to already be there —
    # both are appended in order by the same background thread — but the
    # ack alone can race this assertion right after `start` returns.
    _wait_for_stream_batch(published)
    assert published["stream"][0] == {
        "streaming": True,
        "avg": 16,
        "osr": 6,
        "samples": [],
        "packets": 0,
        "error": "",
    }

    h.on_pmt_stream_stop_request("")
    h._pmt_stream_thread.join(timeout=5)

    assert h._pmt_streaming is False
    assert h._pmt_stream_stop_event is None
    assert published["stream"][-1]["streaming"] is False
    assert published["stream"][-1]["error"] == ""
    assert h.proxy.uart.subscribers == {}
    assert "power 0" in h.log
    assert h.log[-1] == "light restored"


def test_live_stream_start_while_running_is_a_live_update(published, monkeypatch):
    monkeypatch.setattr(mod, "PMT_STREAM_PUBLISH_INTERVAL_S", 0.01)
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_stream_start_request(json.dumps({"gain": 10, "avg": 16, "osr": 6}))
    _wait_for_stream_batch(published)

    h.on_pmt_stream_start_request(json.dumps({"gain": 20, "avg": 32, "osr": 3}))
    # A membership check, not `[-1]`: the background thread's own batch
    # loop keeps publishing concurrently and may append after this ack.
    assert {
        "streaming": True,
        "avg": 32,
        "osr": 3,
        "samples": [],
        "packets": 0,
        "error": "",
    } in published["stream"]
    assert "gain 20" in h.log
    assert "stream 1 32 3" in h.log
    # Still one session: no second thread/claim was taken.
    assert h._pmt_streaming is True

    h.on_pmt_stream_stop_request("")
    h._pmt_stream_thread.join(timeout=5)


def test_stop_live_stream_preempts_running_stream_then_captures(published, monkeypatch):
    monkeypatch.setattr(mod, "PMT_STREAM_PUBLISH_INTERVAL_S", 0.01)
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_stream_start_request(json.dumps({"gain": 10, "avg": 16, "osr": 6}))
    _wait_for_stream_batch(published)

    payload = json.loads(_request([{"slot": 1, "gain": 50, "exposure_s": 1.0}]))
    payload["stop_live_stream"] = True
    _run(h, json.dumps(payload))

    done = published["done"][-1]
    assert done["ok"] is True
    # The stream's own teardown cleared these before the retried claim.
    assert h._pmt_streaming is False
    assert h._pmt_stream_stop_event is None
    assert published["stream"][-1]["streaming"] is False
    # The capture itself ran, after the stream's teardown freed the claim.
    assert "move 2" in h.log and "gain 50" in h.log


def test_capture_without_stop_live_stream_still_refused_while_streaming(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_streaming = True
    h._pmt_stream_stop_event = threading.Event()
    h.on_pmt_capture_request(_request([{"slot": 1, "gain": 10, "exposure_s": 1.0}]))
    assert published["done"][-1]["error"] == "the live stream is running"
    # Never preempted: the stop event is untouched and no capture ran.
    assert not h._pmt_stream_stop_event.is_set()
    assert h.log == []


def test_live_stream_refused_while_capturing(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_capturing = True
    h.on_pmt_stream_start_request(json.dumps({"gain": 10}))
    assert published["stream"] == [
        {
            "streaming": False,
            "avg": PMT_STREAM_AVG,
            "osr": PMT_STREAM_OSR,
            "samples": [],
            "packets": 0,
            "error": "a PMT capture is running",
        }
    ]
    assert h.log == []


def test_live_stream_stop_with_no_stream_running_is_a_no_op(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_stream_stop_request("")
    assert published["stream"] == []


def test_acquire_writes_csv_and_publishes_stats(published, tmp_path):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.proxy.uart.acquire_capture = _PmtCapture([10, 20, 30, 40])
    h.on_pmt_acquire_request(json.dumps({"gain": 90}))
    h._pmt_acquire_thread.join(timeout=5)

    done = published["acquire"][-1]
    assert done["ok"] is True
    assert done["gain"] == 90
    assert done["n_samples"] == 4
    assert done["mean_counts"] == pytest.approx(25.0)
    assert done["packets_received"] == 4 and done["packets_expected"] == 4
    assert done["csv_path"] != ""
    assert Path(done["csv_path"]).exists()
    assert "adc_diag" in h.log
    assert "acquire_collect" in h.log
    assert "power 0" in h.log
    assert h.log[-1] == "light restored"
    assert h._pmt_acquiring is False


def test_acquire_incomplete_collect_is_not_ok_but_still_saves(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.proxy.uart.acquire_capture = _PmtCapture([1, 2, 3], n_expected=10)
    h.on_pmt_acquire_request(json.dumps({"gain": 5}))
    h._pmt_acquire_thread.join(timeout=5)

    done = published["acquire"][-1]
    assert done["ok"] is False
    assert done["csv_path"] != ""
    assert "incomplete" in done["error"]


def test_acquire_refused_while_capturing(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h._pmt_capturing = True
    h.on_pmt_acquire_request(json.dumps({"gain": 50}))
    assert published["acquire"] == [
        {
            "ok": False,
            "gain": 50,
            "n_samples": 0,
            "mean_counts": 0.0,
            "sd_counts": 0.0,
            "min_counts": 0,
            "max_counts": 0,
            "packets_received": 0,
            "packets_expected": 0,
            "adc_full_scale": PMT_ADC_FULL_SCALE,
            "rf_ohms": PMT_RF_OHMS,
            "csv_path": "",
            "error": "a PMT capture is running",
        }
    ]
    assert h.log == []


def test_acquire_old_single_gain_payload_still_validates(published):
    h = _Harness()
    h.proxy = _Session(h.log)
    h.on_pmt_acquire_request(json.dumps({"gain": 42}))
    h._pmt_acquire_thread.join(timeout=5)
    done = published["acquire"][-1]
    assert done["gain"] == 42
    assert done["rf_ohms"] == pytest.approx(PMT_RF_OHMS)


# --------------------------------------------------------------------- #
# Unknown motor firmware and the renumbered spot table                   #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("spot", ["0", "2"])
def test_moves_are_refused_while_the_motor_firmware_stays_unknown(published, spot):
    h = _Harness(motor_firmware=None)
    h.proxy = _Session(h.log)

    h.on_pmt_move_to_spot_request(spot)

    # The version was asked for (the monitor re-reads it), then nothing moved.
    assert h.firmware_queries >= 1
    assert h.log == []
    assert len(h.errors) == 1 and "firmware version is unknown" in h.errors[0]


def test_spots_read_is_refused_while_the_motor_firmware_stays_unknown(published):
    h = _Harness(motor_firmware=None)
    h.proxy = _Session(h.log)

    h.on_pmt_spots_read_request("")

    assert published["spots"] == []
    assert len(h.errors) == 1 and "firmware version is unknown" in h.errors[0]


def test_capture_fails_its_spots_while_the_motor_firmware_stays_unknown(published):
    h = _Harness(motor_firmware=None)
    h.proxy = _Session(h.log)

    _run(h, _request([{"slot": 1, "gain": 50, "exposure_s": 1.0}]))

    assert not any(entry.startswith("move") for entry in h.log)
    assert "firmware version is unknown" in published["done"][-1]["results"][0]["error"]


@pytest.mark.parametrize(
    "locations, park, warned",
    [
        # Location 1 at home: the old park slot, never re-taught.
        ((0, 1000, 0, 24500, 0, 0), (0, 0), True),
        # Location 1 at the park position (absolute, or following location 1).
        ((5000, 1000, 0, 24500, 0, 0), (0, 5000), True),
        ((5000, 1000, 0, 24500, 0, 0), (1, 0), True),
        # Re-taught: location 1 is a real spot away from park.
        ((5000, 1000, 0, 24500, 0, 0), (0, 0), False),
        # Park unreadable: only the zero test applies.
        ((5000, 1000, 0, 24500, 0, 0), None, False),
    ],
)
def test_preset_firmware_warns_of_a_location_one_left_over_from_park(
    published, locations, park, warned
):
    h = _Harness(motor_firmware=PMT_PRESET_PARK_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)
    h.proxy.uart.pmt_locations = locations
    h.proxy.uart.pmt_park = park

    h.on_pmt_spots_read_request("")

    warnings = [e for e in h.errors if e.startswith("PMT spot table check")]
    assert bool(warnings) is warned
    assert published["spots"]

    if warned:
        assert "re-check saved PMT protocol steps" in warnings[0]


def test_the_location_one_warning_is_given_once_per_connection(published):
    h = _Harness(motor_firmware=PMT_PRESET_PARK_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)

    h.on_pmt_spots_read_request("")
    h.on_pmt_spots_read_request("")

    assert len(h.errors) == 1
    assert h.log.count("read park") == 1

    # A new connection (a new session) warns again.
    h.proxy = _Session(h.log)
    h.on_pmt_spots_read_request("")

    assert len(h.errors) == 2


def test_older_firmware_never_checks_location_one(published):
    h = _Harness(motor_firmware=_LEGACY_MOTOR_FIRMWARE)
    h.proxy = _Session(h.log)

    h.on_pmt_spots_read_request("")

    assert h.errors == []
    assert "read park" not in h.log


@pytest.mark.parametrize(
    "motor_firmware, spot",
    [(PMT_PRESET_PARK_MOTOR_FIRMWARE, "2"), (PMT_PRESET_PARK_MOTOR_FIRMWARE, "0")],
)
def test_pmt_moves_and_parks_run_outside_the_proxy_lock(
    published, motor_firmware, spot
):
    h = _Harness(motor_firmware=motor_firmware)
    h.proxy = _Session(h.log)

    h.on_pmt_move_to_spot_request(spot)

    assert h.unserialized == [f"PMT move to spot {spot}"]
