# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Qt-free electrode zones model."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.consts import ZONES_KEY
from device_viewer.default_settings import alpha_keys, default_alphas, zones_key

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


def test_zones_alpha_key_registered():
    assert zones_key == "Zones"
    assert zones_key in alpha_keys
    assert default_alphas[zones_key] == 100
    assert ZONES_KEY == "microdrop.device.zones"


@pytest.fixture
def device():
    """(polygons, id->channel, neighbours) for the bundled 2x3 device."""
    from device_viewer.models.electrodes import Electrodes

    electrodes = Electrodes()
    electrodes.set_electrodes_from_svg_file(str(BUNDLED_2X3))
    svg = electrodes.svg_model
    return svg.polygons, electrodes.electrode_ids_channels_map, svg.neighbours


@pytest.fixture
def manager(device):
    from device_viewer.models.zones import ZoneLayerManager

    manager = ZoneLayerManager()
    manager.set_device(*device)
    manager.add_zone_type("heating", "#f5e050")
    manager.selected_zone_type = manager.zone_types[0]
    return manager


def test_zone_ids_are_stable_and_unique(manager):
    second = manager.add_zone_type("heating", "#e06666")
    assert [zone.id for zone in manager.zone_types] == ["heating", "heating-2"]
    assert second.name == "heating"


def test_capture_touching_selects_any_overlap(manager):
    polygons = manager.electrode_polygons
    first_id = sorted(polygons)[0]
    min_x, min_y, max_x, max_y = polygons[first_id].bounds
    # A box covering only a sliver inside the first electrode captures it.
    captured = manager.capture_electrode_ids_touching(
        min_x + 0.1, min_y + 0.1, min_x + 0.2, min_y + 0.2
    )
    assert captured == [first_id]
    # A box far outside every electrode captures nothing.
    assert (
        manager.capture_electrode_ids_touching(
            max_x + 1000, max_y + 1000, max_x + 1001, max_y + 1001
        )
        == []
    )


def test_commit_creates_region_with_channels(manager):
    ids = sorted(manager.electrode_polygons)[:2]
    manager.add_to_pending(ids)
    region = manager.commit_pending_region()
    assert region is not None
    assert region.electrode_ids == ids
    assert region.channels == sorted(
        manager.electrode_id_to_channel_map[i] for i in ids
    )
    assert manager.pending_electrode_ids == []
    assert manager.region_count("heating") == 1
    assert manager.zone_types[0].region_count == 1


def test_toggle_electrode_sculpts_pending(manager):
    first_id = sorted(manager.electrode_polygons)[0]
    manager.toggle_electrode_in_pending(first_id)
    assert manager.pending_electrode_ids == [first_id]
    manager.toggle_electrode_in_pending(first_id)
    assert manager.pending_electrode_ids == []


def test_disjoint_commit_splits_by_contiguity(manager):
    neighbours = manager.electrode_neighbours
    ids = sorted(manager.electrode_polygons)
    first_id = ids[0]
    # Pick an electrode that is NOT adjacent to the first one.
    far_id = next(
        i for i in ids if i != first_id and i not in neighbours.get(first_id, [])
    )
    manager.add_to_pending([first_id, far_id])
    manager.commit_pending_region()
    assert len(manager.regions) == 2
    assert {tuple(r.electrode_ids) for r in manager.regions} == {
        (first_id,),
        (far_id,),
    }


def test_region_ids_are_monotonic(manager):
    ids = sorted(manager.electrode_polygons)
    manager.add_to_pending([ids[0]])
    first = manager.commit_pending_region()
    manager.remove_region(first)
    manager.add_to_pending([ids[1]])
    second = manager.commit_pending_region()
    assert first.id == "heating-1"
    assert second.id == "heating-2"


def test_region_outline_covers_members(manager):
    ids = sorted(manager.electrode_polygons)[:2]
    manager.add_to_pending(ids)
    region = manager.commit_pending_region()
    outline = manager.region_outline(region)
    for electrode_id in ids:
        assert outline.buffer(1e-6).contains(manager.electrode_polygons[electrode_id])


def test_channels_for_is_union(manager):
    ids = sorted(manager.electrode_polygons)
    manager.add_to_pending(ids[:2])
    manager.commit_pending_region()
    manager.add_to_pending(ids[1:3])
    manager.commit_pending_region()
    expected = sorted({manager.electrode_id_to_channel_map[i] for i in ids[:3]})
    assert manager.channels_for("heating") == expected


def test_records_round_trip(manager):
    ids = sorted(manager.electrode_polygons)
    manager.add_to_pending(ids[:2])
    region = manager.commit_pending_region()
    region.visible = False
    records = manager.to_records()
    assert records == [
        {
            "id": "heating-1",
            "zone_id": "heating",
            "zone_name": "heating",
            "zone_color": "#f5e050",
            "visible": False,
            "electrode_ids": ids[:2],
        }
    ]
    fresh = type(manager)()
    fresh.set_device(
        manager.electrode_polygons,
        manager.electrode_id_to_channel_map,
        manager.electrode_neighbours,
    )
    fresh.load_records(records)
    assert [z.id for z in fresh.zone_types] == ["heating"]
    assert fresh.zone_types[0].color == "#f5e050"
    assert [r.id for r in fresh.regions] == ["heating-1"]
    assert fresh.regions[0].visible is False
    # Counters resume after loaded ids: the next region is heating-2.
    fresh.selected_zone_type = fresh.zone_types[0]
    fresh.add_to_pending([ids[2]])
    assert fresh.commit_pending_region().id == "heating-2"


def test_snapshot_for_app_globals(manager):
    ids = sorted(manager.electrode_polygons)
    manager.add_to_pending(ids[:2])
    manager.commit_pending_region()
    snapshot = manager.snapshot_for_app_globals()
    assert snapshot == {
        "heating": {
            "name": "heating",
            "color": "#f5e050",
            "regions": [
                {
                    "id": "heating-1",
                    "electrode_ids": ids[:2],
                    "channels": sorted(
                        manager.electrode_id_to_channel_map[i] for i in ids[:2]
                    ),
                }
            ],
        }
    }


def test_cancel_current_interaction_order(manager):
    ids = sorted(manager.electrode_polygons)
    manager.add_to_pending(ids[:1])
    region = manager.commit_pending_region()
    manager.selected_region = region
    manager.begin_edit_region(region)
    assert manager.cancel_current_interaction() is True
    assert manager.editing_region is None
    assert manager.pending_electrode_ids == []
    assert manager.selected_region is region
    assert manager.cancel_current_interaction() is True
    assert manager.selected_region is None
    assert manager.cancel_current_interaction() is False


def test_every_mutation_fires_one_undo_snapshot(manager):
    fired = []
    manager.observe(lambda event: fired.append(event), "undo_snapshot_pushed")
    ids = sorted(manager.electrode_polygons)
    manager.add_to_pending(ids[:1])
    region = manager.commit_pending_region()
    manager.change_region_zone(region, manager.add_zone_type("mixing").id)
    manager.remove_region(region)
    # commit, add type, change zone, remove: four snapshots, none for undo.
    assert len(fired) == 4
    assert manager.undo() is True
    assert len(fired) == 4


def test_remove_zone_type_cascades(manager):
    ids = sorted(manager.electrode_polygons)
    manager.add_to_pending(ids[:1])
    manager.commit_pending_region()
    manager.remove_zone_type("heating")
    assert manager.zone_types == []
    assert manager.regions == []
    assert manager.active_zone_id == ""
