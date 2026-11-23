# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The motor mechanical param blob: every firmware generation (56 / 64 / 68 /
72 B) decodes and writes back at its own length, speeds travel in real µm/s
with an unchanged speed kept bit-exact, and the system mixin's write is a
read-modify-write of the served blob. Hardware-free, no Redis."""

# Standard library imports.
import json

# Third-party imports.
import pytest
from dropbot_portable.param_layout import (
    MOTOR_BLOB_SIZES,
    MOTOR_FIELDS,
    MOTOR_LEGACY_SPEED_FACTOR,
    decode_motor_blob,
    encode_motor_blob,
)

# Enthought library imports.
from traits.api import Any, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.consts import MOTOR_PARAM_FIELDS
from portable_dropbot_controller.motor_params import (
    decode_motor_params,
    encode_motor_params,
    served_motor_fields,
)
from portable_dropbot_controller.services import (
    portable_dropbot_system_mixin_service as system_service,
)

#: A plausible current-generation tray struct.
BOARD_FIELDS = {
    "nl_pos": -500.0,
    "pl_pos": 64000.0,
    "round_len": 2000.0,
    "origin_offset": 250.0,
    "origin_area": 1500.0,
    "step_len": 0.625,
    "motor_polarity": 1,
    "I_hold": 8,
    "I_run": 20,
    "subdiv": 16,
    "run_sgt": 5,
    "rst_sgt": 3,
    "bspd": 7000,
    "rspd": 20000,
    "acc_run": 6,
    "acc_rst": 6,
    "stealthchop": 0,
    "home_dir": 1,
}


def _served_blob(size):
    """What firmware of one generation serves: a prefix of the struct."""
    return encode_motor_blob(BOARD_FIELDS)[:size]


def test_field_names_mirror_the_driver_layout():
    assert MOTOR_PARAM_FIELDS == tuple(name for name, _ in MOTOR_FIELDS)


@pytest.mark.parametrize("size", MOTOR_BLOB_SIZES)
def test_unedited_round_trip_is_byte_identical(size):
    blob = _served_blob(size)
    fields = decode_motor_params(blob, MOTOR_LEGACY_SPEED_FACTOR)
    served = served_motor_fields(blob)
    edits = {name: fields[name] for name in served}

    assert len(served) == size // 4
    assert encode_motor_params(blob, edits, MOTOR_LEGACY_SPEED_FACTOR) == blob


@pytest.mark.parametrize("size", MOTOR_BLOB_SIZES)
def test_an_edit_is_written_back_at_the_served_length(size):
    blob = _served_blob(size)

    packed = encode_motor_params(blob, {"I_run": 24}, 1.0)

    assert len(packed) == size
    assert packed[32:36] != blob[32:36]
    assert packed[:32] == blob[:32] and packed[36:] == blob[36:]


def test_legacy_speeds_show_and_write_in_real_um_per_s():
    blob = _served_blob(64)
    fields = decode_motor_params(blob, MOTOR_LEGACY_SPEED_FACTOR)

    assert fields["rspd"] == round(20000 * MOTOR_LEGACY_SPEED_FACTOR)

    packed = encode_motor_params(blob, {"rspd": 10000}, MOTOR_LEGACY_SPEED_FACTOR)
    wire = decode_motor_blob(packed)

    assert wire["rspd"] == round(10000 / MOTOR_LEGACY_SPEED_FACTOR)
    assert wire["bspd"] == 7000


def test_a_field_the_firmware_does_not_serve_is_refused():
    with pytest.raises(ValueError, match="home_dir is not served"):
        encode_motor_params(_served_blob(68), {"home_dir": 0}, 1.0)


def test_a_value_the_firmware_refuses_is_refused():
    with pytest.raises(ValueError, match="home_dir 2"):
        encode_motor_params(_served_blob(72), {"home_dir": 2}, 1.0)

    with pytest.raises(ValueError, match="subdiv 12"):
        encode_motor_params(_served_blob(72), {"subdiv": 12}, 1.0)


def test_an_unknown_blob_size_is_refused():
    with pytest.raises(ValueError, match="52 B"):
        decode_motor_params(_served_blob(52), 1.0)


# --------------------------------------------------------------------- #
# The system mixin's read / write requests                              #
# --------------------------------------------------------------------- #


class _SpeedUnits:
    def __init__(self, factor, confirmed=True):
        self.factor = factor
        self.confirmed = confirmed

    def describe(self):
        return "test units"


class _Uart:
    def __init__(self, blob, units):
        self.blob = blob
        self.units = units
        self.writes = []

    def getBoardParameter(self, board, param):
        return b"_mt_cabin_dp\x00" + self.blob

    def motor_speed_units(self):
        return self.units

    def setParams(self, board, key, value):
        self.writes.append((board, key, value))

        return True


class _Session:
    def __init__(self, blob, units):
        self.uart = _Uart(blob, units)


class _Base(HasTraits):
    proxy = Any()

    def _proxy_call(self, context, call):
        return True, call()


class _Harness(system_service.PortableDropbotSystemMixinService, _Base):
    pass


@pytest.fixture
def published(monkeypatch):
    sent = []
    monkeypatch.setattr(
        system_service,
        "publish_message",
        lambda topic, message: sent.append(json.loads(message)),
    )

    return sent


def _harness(size, units):
    harness = _Harness()
    harness.proxy = _Session(_served_blob(size), units)

    return harness


@pytest.mark.parametrize("size", MOTOR_BLOB_SIZES)
def test_read_publishes_the_served_fields(size, published):
    harness = _harness(size, _SpeedUnits(1.0))

    harness.on_motor_params_read_request("tray")

    [update] = published

    assert list(update["fields"]) == list(MOTOR_PARAM_FIELDS[: size // 4])
    assert update["blob_size"] == size


@pytest.mark.parametrize("size", MOTOR_BLOB_SIZES)
def test_write_sends_the_whole_blob_at_the_served_length(size, published):
    harness = _harness(size, _SpeedUnits(1.0))

    harness.on_motor_params_write_request(
        json.dumps({"motor": "tray", "fields": {"I_run": 24}})
    )

    [(board, key, packed)] = harness.proxy.uart.writes

    assert (board, key, len(packed)) == ("motor", "_mt_cabin_dp", size)
    assert decode_motor_blob(packed)["I_run"] == 24
    assert published == [{"motor": "tray", "written": True}]


def test_write_is_refused_while_the_speed_units_are_unconfirmed(published):
    harness = _harness(72, _SpeedUnits(MOTOR_LEGACY_SPEED_FACTOR, confirmed=False))

    harness.on_motor_params_write_request(
        json.dumps({"motor": "tray", "fields": {"I_run": 24}})
    )

    assert harness.proxy.uart.writes == []
    assert "speed units unknown" in published[0]["error"]
