# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera-alignment presets store: the JSON library, its per-device
naming and default rules, and the one-time endpoint-cache migration."""

# Standard library imports.
import json
import os
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.consts import ALIGNMENT_PRESETS_SCHEMA_VERSION
from device_viewer.models.alignment_preset import AlignmentPreset
from device_viewer.models.alignment_preset_store import AlignmentPresetStore
from device_viewer.utils.camera_endpoints import CameraEndpointStore

ENDPOINT = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]
SCENE_QUAD = [[2.0, 1.0], [98.0, 3.0], [99.0, 79.0], [1.0, 78.0]]
CAMERA_QUAD = [[100.0, 50.0], [500.0, 60.0], [490.0, 400.0], [110.0, 390.0]]


def _snapshot(device_key="chip-a", camera_quad=CAMERA_QUAD):
    return AlignmentPreset(
        device_key=device_key,
        device_scene_rect=[0.0, 0.0, 100.0, 80.0],
        camera_label="Cam 1",
        frame_size=[640.0, 480.0],
        camera_quad=camera_quad,
        scene_quad=SCENE_QUAD,
        endpoint_quad=ENDPOINT,
    )


@pytest.fixture
def endpoint_store(tmp_path):
    return CameraEndpointStore(path=tmp_path / "camera_endpoints.json")


@pytest.fixture
def store(tmp_path, endpoint_store):
    store = AlignmentPresetStore(
        path=tmp_path / "alignment_presets.json", endpoint_store=endpoint_store
    )
    store.refresh()

    return store


def test_save_round_trips_every_field(store, tmp_path):
    saved = store.save_named("  bench  ", _snapshot())

    reread = AlignmentPresetStore(path=store.path, endpoint_store=store.endpoint_store)
    reread.refresh()
    preset = reread.get(saved.id)

    assert preset.to_dict() == saved.to_dict()
    assert preset.name == "bench"
    assert preset.kind == "named"
    assert preset.scope == "device"
    assert preset.camera_quad == CAMERA_QUAD
    assert preset.scene_quad == SCENE_QUAD
    assert preset.endpoint_quad == ENDPOINT
    assert preset.frame_size == [640.0, 480.0]


def test_file_carries_the_schema_version(store):
    store.save_named("bench", _snapshot())

    data = json.loads(store.path.read_text(encoding="utf-8"))

    assert data["schema_version"] == ALIGNMENT_PRESETS_SCHEMA_VERSION
    assert set(data) == {"schema_version", "presets", "defaults"}


def test_endpoint_only_preset_round_trips(store):
    saved = store.save_named("bare", _snapshot(camera_quad=None))

    store.refresh()

    assert store.get(saved.id).is_endpoint_only


def test_corrupt_file_reads_empty_and_is_kept_aside_on_write(store):
    store.path.write_text("{not json", encoding="utf-8")

    store.refresh()

    assert store.presets == []

    store.save_named("bench", _snapshot())

    assert [preset.name for preset in store.presets] == ["bench"]
    assert store.path.with_name(f"{store.path.name}.unreadable").read_text(
        encoding="utf-8"
    ) == ("{not json")


def test_newer_schema_lists_but_refuses_writes(store):
    record = _snapshot().to_dict()
    record.update(id="future", name="from the future")
    store.path.write_text(
        json.dumps(
            {
                "schema_version": ALIGNMENT_PRESETS_SCHEMA_VERSION + 1,
                "presets": [record],
                "defaults": [],
            }
        ),
        encoding="utf-8",
    )

    store.refresh()

    assert store.read_only
    assert [preset.name for preset in store.presets] == ["from the future"]

    with pytest.raises(ValueError):
        store.save_named("bench", _snapshot())


def test_a_failed_write_leaves_the_file_and_no_aside_file(store, monkeypatch):
    store.save_named("bench", _snapshot())
    before = store.path.read_bytes()

    def locked(source, destination):
        raise PermissionError("held by another process")

    monkeypatch.setattr("microdrop_utils.file_handler.ATOMIC_WRITE_RETRY_DELAY_S", 0)
    monkeypatch.setattr(os, "replace", locked)

    with pytest.raises(OSError):
        store.save_named("second", _snapshot())

    assert store.path.read_bytes() == before
    assert sorted(path.name for path in store.path.parent.iterdir()) == [
        store.path.name
    ]


def test_a_briefly_locked_file_is_written_on_a_retry(store, monkeypatch):
    real_replace = os.replace
    refusals = []

    def locked_once(source, destination):
        if not refusals:
            refusals.append(destination)

            raise PermissionError("held by another process")

        real_replace(source, destination)

    monkeypatch.setattr("microdrop_utils.file_handler.ATOMIC_WRITE_RETRY_DELAY_S", 0)
    monkeypatch.setattr(os, "replace", locked_once)

    store.save_named("bench", _snapshot())

    assert refusals
    assert [preset.name for preset in store.presets] == ["bench"]


def test_unknown_record_fields_survive_a_rewrite(store):
    saved = store.save_named("bench", _snapshot())
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["presets"][0]["future_field"] = 42
    store.path.write_text(json.dumps(data), encoding="utf-8")

    store.rename(saved.id, "renamed")

    data = json.loads(store.path.read_text(encoding="utf-8"))

    assert data["presets"][0]["future_field"] == 42


def test_names_are_unique_per_device_case_insensitively(store):
    store.save_named("Bench", _snapshot("chip-a"))
    store.save_named("bench", _snapshot("chip-b"))

    with pytest.raises(ValueError):
        store.save_named("BENCH", _snapshot("chip-a"))

    assert store.name_error("bench ", "chip-a")
    assert not store.name_error("bench", "chip-c")
    assert store.find_named("chip-a", "BENCH").name == "Bench"


def test_invalid_names_are_refused(store):
    assert store.name_error("   ", "chip-a")
    assert store.name_error("tab\there", "chip-a")

    with pytest.raises(ValueError):
        store.save_named("", _snapshot())


def test_replace_keeps_identity_and_default(store):
    first = store.save_named("bench", _snapshot())
    store.set_default(first.id)

    replaced = store.save_named("BENCH", _snapshot(camera_quad=None), replace=True)

    assert replaced.id == first.id
    assert replaced.is_endpoint_only
    assert len(store.named_for("chip-a")) == 1
    assert store.resolve_default("chip-a").id == first.id


def test_rename_keeps_identity_and_default(store):
    preset = store.save_named("bench", _snapshot())
    store.set_default(preset.id)

    store.rename(preset.id, "renamed")

    assert store.get(preset.id).name == "renamed"
    assert store.resolve_default("chip-a").id == preset.id


def test_rename_onto_a_sibling_name_is_refused(store):
    store.save_named("one", _snapshot())
    two = store.save_named("two", _snapshot())

    with pytest.raises(ValueError):
        store.rename(two.id, "ONE")

    # A case-only rename of itself is no clash.
    store.rename(two.id, "TWO")

    assert store.get(two.id).name == "TWO"


def test_delete_drops_the_preset_and_its_default(store):
    preset = store.save_named("bench", _snapshot())
    store.set_default(preset.id)

    store.delete(preset.id)

    assert store.get(preset.id) is None
    assert store.resolve_default("chip-a") is None
    assert store.defaults == []


def test_one_default_per_device(store):
    one = store.save_named("one", _snapshot("chip-a"))
    two = store.save_named("two", _snapshot("chip-a"))
    other = store.save_named("other", _snapshot("chip-b"))

    store.set_default(one.id)
    store.set_default(other.id)
    store.set_default(two.id)

    assert store.resolve_default("chip-a").id == two.id
    assert store.resolve_default("chip-b").id == other.id
    assert not store.is_default(one.id)
    assert len(store.defaults) == 2

    store.clear_default("chip-a")

    assert store.resolve_default("chip-a") is None
    assert store.resolve_default("chip-b").id == other.id


def test_resolve_default_falls_back_to_the_device_wide_slot(store):
    preset = store.save_named("bench", _snapshot())
    store.set_default(preset.id)

    assert store.resolve_default("chip-a", camera_label="Some camera").id == preset.id
    assert store.resolve_default("chip-z") is None


def test_next_default_name_counts_per_device(store):
    assert store.next_default_name("chip-a") == "alignment-1"

    store.save_named("alignment-1", _snapshot("chip-a"))

    assert store.next_default_name("chip-a") == "alignment-2"
    assert store.next_default_name("chip-b") == "alignment-1"


def test_migration_turns_endpoints_into_default_presets(tmp_path, endpoint_store):
    endpoint_store.save("chip-a", ENDPOINT)
    endpoint_store.save("chip-b", ENDPOINT)
    endpoints_before = endpoint_store.path.read_bytes()
    saved_at = endpoint_store.saved_at("chip-a")

    store = AlignmentPresetStore(
        path=tmp_path / "presets" / "alignment_presets.json",
        endpoint_store=endpoint_store,
    )
    store.refresh()

    preset = store.resolve_default("chip-a")

    assert preset.name == "chip-a endpoint"
    assert preset.is_endpoint_only
    assert preset.endpoint_quad == ENDPOINT
    assert preset.scene_quad == ENDPOINT
    assert preset.saved_at == saved_at
    assert store.resolve_default("chip-b").name == "chip-b endpoint"
    assert endpoint_store.path.read_bytes() == endpoints_before


def test_migration_is_idempotent(tmp_path, endpoint_store):
    endpoint_store.save("chip-a", ENDPOINT)
    store = AlignmentPresetStore(
        path=tmp_path / "alignment_presets.json", endpoint_store=endpoint_store
    )

    store.refresh()
    store.refresh()

    assert [preset.name for preset in store.presets] == ["chip-a endpoint"]
    assert len(store.defaults) == 1


def test_migration_covers_devices_aligned_after_the_file_exists(store):
    store.save_named("bench", _snapshot("chip-a"))

    # A device that already has presets is left alone; a new one is covered.
    store.endpoint_store.save("chip-a", SCENE_QUAD)
    store.endpoint_store.save("chip-b", ENDPOINT)
    store.refresh()
    store.refresh()

    assert sorted((preset.device_key, preset.name) for preset in store.presets) == [
        ("chip-a", "bench"),
        ("chip-b", "chip-b endpoint"),
    ]
    assert store.resolve_default("chip-b").endpoint_quad == ENDPOINT
    assert store.resolve_default("chip-a") is None


def test_migration_reruns_after_an_unreadable_file_is_set_aside(store):
    store.endpoint_store.save("chip-a", ENDPOINT)
    store.refresh()
    store.path.write_text("{garbage", encoding="utf-8")

    store.refresh()

    assert [preset.name for preset in store.presets] == ["chip-a endpoint"]
    assert store.resolve_default("chip-a") is not None
    assert store.unreadable_copy


def test_repeated_unreadable_files_keep_every_copy(store):
    copies = []

    for garbage in ("{first", "{second", "{third"):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(garbage, encoding="utf-8")
        store.refresh()
        copies.append(store.unreadable_copy)

    assert len(set(copies)) == 3
    assert [Path(copy).read_text(encoding="utf-8") for copy in copies] == [
        "{first",
        "{second",
        "{third",
    ]


def test_newer_reshaped_schema_stays_byte_identical_and_read_only(store):
    store.endpoint_store.save("chip-a", ENDPOINT)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    future = json.dumps(
        {"schema_version": ALIGNMENT_PRESETS_SCHEMA_VERSION + 1, "presets": {}}
    ).encode("utf-8")
    store.path.write_bytes(future)

    store.refresh()

    assert store.read_only
    assert "newer" in store.read_only_reason
    assert store.presets == []

    with pytest.raises(ValueError):
        store.save_named("bench", _snapshot())

    with pytest.raises(ValueError):
        store.clear_default("chip-a")

    store.refresh()

    assert store.path.read_bytes() == future
    assert not store.unreadable_copy


def test_replace_keeps_unknown_fields(store):
    store.save_named("bench", _snapshot())
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["presets"][0]["future_field"] = 42
    store.path.write_text(json.dumps(data), encoding="utf-8")

    store.save_named("bench", _snapshot(camera_quad=None), replace=True)

    record = json.loads(store.path.read_text(encoding="utf-8"))["presets"][0]

    assert record["future_field"] == 42
    assert record["camera_quad"] is None


def test_unique_name_counts_up(store):
    assert store.unique_name("chip-a", "Before x") == "Before x"

    store.save_named("Before x", _snapshot())

    assert store.unique_name("chip-a", "before X") == "before X (2)"


def test_no_endpoints_writes_no_file(store):
    assert not store.path.exists()
    assert store.presets == []
