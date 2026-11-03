# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The magnet engage height requests: read publishes z_up in mm, a write
replaces only z_up (mm -> µm) in the read-back device defaults and is
refused above the magnet-Z soft limit, preset persists _dp_magnet.
Hardware-free, no Redis."""

# Standard library imports.
import struct

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    MAGNET_DEFAULTS_FORMAT,
    MOTOR_PARAM_FIELDS,
    MagnetEngageUpdated,
)
from portable_dropbot_controller.services import (
    portable_dropbot_system_mixin_service as system_service,
)

#: z_up, z_down, y_0, y_space (µm) the fake board starts with.
BOARD_MAGNET_DEFAULTS = (12500, 300, 4100, 9000)

#: The fake magnet-Z motor's positive soft limit (µm).
SOFT_LIMIT_UM = 16000.0


def _motor_blob(pl_pos):
    """A 16-field mechanical param struct with this pl_pos."""
    values = [0.0, pl_pos, 0.0, 0.0, 0.0, 0.0] + [0] * 10
    fmt = ">" + "".join(fmt for _, fmt in MOTOR_PARAM_FIELDS)

    return struct.pack(fmt, *values)


class _Uart:
    def __init__(self):
        self.magnet = struct.pack(MAGNET_DEFAULTS_FORMAT, *BOARD_MAGNET_DEFAULTS)
        self.writes = []
        self.presets = []

    def getBoardParameter(self, board, param):
        blobs = {
            "magnet_defaults": (b"_dp_magnet", self.magnet),
            "magnet_motor": (b"_mt_z_dp", _motor_blob(SOFT_LIMIT_UM)),
        }
        key, blob = blobs[param]

        return key + b"\x00" + blob

    def setParams(self, board, key, value):
        self.writes.append((board, key, value))

        return True

    def presetParams(self, board, key):
        self.presets.append((board, key))

        return True


class _Session:
    def __init__(self):
        self.uart = _Uart()


class _Base(HasTraits):
    proxy = Any()

    def _proxy_call(self, context, call):
        return True, call()


class _Harness(system_service.PortableDropbotSystemMixinService, _Base):
    pass


class _Publisher:
    def __init__(self):
        self.published = []

    def publish(self, payload):
        self.published.append(MagnetEngageUpdated.model_validate(payload))


@pytest.fixture
def published(monkeypatch):
    publisher = _Publisher()
    monkeypatch.setattr(system_service, "magnet_engage_updated_publisher", publisher)

    return publisher.published


@pytest.fixture
def harness():
    h = _Harness()
    h.proxy = _Session()

    return h


def test_read_publishes_the_engage_height_in_mm(harness, published):
    harness.on_magnet_engage_read_request("")

    assert published == [MagnetEngageUpdated(action="read", engage_mm=12.5)]


def test_write_replaces_only_z_up_and_keeps_the_other_fields(harness, published):
    harness.on_magnet_engage_write_request('{"engage_mm": 14.0004}')

    [(board, key, packed)] = harness.proxy.uart.writes

    assert (board, key) == ("motor", "_dp_magnet")
    assert struct.unpack(MAGNET_DEFAULTS_FORMAT, packed) == (14000, 300, 4100, 9000)
    assert published == [MagnetEngageUpdated(action="write", engage_mm=14.0)]


def test_write_above_the_soft_limit_is_refused(harness, published):
    harness.on_magnet_engage_write_request('{"engage_mm": 16.5}')

    assert harness.proxy.uart.writes == []
    assert published[0].action == "write"
    assert "soft limit (16.000 mm)" in published[0].error


def test_write_of_a_negative_height_is_refused(harness, published):
    harness.on_magnet_engage_write_request('{"engage_mm": -1}')

    assert harness.proxy.uart.writes == []
    assert published[0].error.startswith("invalid height")


def test_preset_persists_the_magnet_defaults_key(harness, published):
    harness.on_magnet_engage_preset_request("")

    assert harness.proxy.uart.presets == [("motor", "_dp_magnet")]
    assert published == [MagnetEngageUpdated(action="preset")]
