# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The per-device camera-alignment endpoint cache: save/load
round-trips, per-device isolation, and resilience to a missing or
corrupt cache file."""
import json

import pytest

from device_viewer.utils.camera_endpoints import CameraEndpointStore

QUAD = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]
OTHER_QUAD = [[5.0, 5.0], [95.0, 5.0], [95.0, 75.0], [5.0, 75.0]]


@pytest.fixture
def store(tmp_path):
    return CameraEndpointStore(path=tmp_path / "endpoints.json")


def test_save_then_load_round_trips(store):
    store.save("device_a", QUAD)
    assert store.load("device_a") == QUAD


def test_load_unknown_device_is_none(store):
    assert store.load("never_saved") is None


def test_endpoints_are_per_device(store):
    store.save("device_a", QUAD)
    store.save("device_b", OTHER_QUAD)
    assert store.load("device_a") == QUAD
    assert store.load("device_b") == OTHER_QUAD
    assert store.device_keys() == ["device_a", "device_b"]


def test_resave_overwrites(store):
    store.save("device_a", QUAD)
    store.save("device_a", OTHER_QUAD)
    assert store.load("device_a") == OTHER_QUAD


def test_remove(store):
    store.save("device_a", QUAD)
    store.remove("device_a")
    assert store.load("device_a") is None
    store.remove("device_a")  # removing again is a no-op


def test_save_rejects_non_quads(store):
    with pytest.raises(ValueError):
        store.save("device_a", QUAD[:3])
    with pytest.raises(ValueError):
        store.save("", QUAD)


def test_quad_points_are_coerced_to_floats(store):
    store.save("device_a", [(0, 0), (10, 0), (10, 8), (0, 8)])
    assert store.load("device_a") == [[0.0, 0.0], [10.0, 0.0],
                                      [10.0, 8.0], [0.0, 8.0]]


def test_corrupt_file_reads_as_empty(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    assert store.load("device_a") is None
    # ...and saving over it recovers the cache.
    store.save("device_a", QUAD)
    assert store.load("device_a") == QUAD


def test_malformed_stored_quad_is_ignored(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps({"device_a": {"scene_quad": [[1, 2]]}}),
        encoding="utf-8")
    assert store.load("device_a") is None


def test_saved_entry_carries_timestamp(store):
    store.save("device_a", QUAD)
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert "saved_at" in data["device_a"]
