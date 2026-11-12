# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure region selection for the Zone Target column (#965)."""

# Third-party imports.
import pytest

# Microdrop package imports.
from zone_protocol_controls.consts import ZoneCriterion
from zone_protocol_controls.zone_selection import (
    region_channels,
    select_zone_region,
    zone_detection_channels,
    zone_regions,
)

MAPPING = {"a1": 1, "a2": 2, "b1": 3, "c1": 4, "c2": 5, "x": None}

SNAPSHOT = {
    "storage": {
        "name": "storage",
        "color": "#f5e050",
        "regions": [
            {"id": "storage-1", "electrode_ids": ["a1", "a2"], "channels": [1, 2]},
            {"id": "storage-2", "electrode_ids": ["b1"], "channels": [3]},
            {"id": "storage-3", "electrode_ids": ["c1", "c2"], "channels": [4, 5]},
        ],
    },
    "empty": {"name": "empty", "color": "#000000", "regions": []},
}


def _ids(region):
    return region["id"] if region is not None else None


def test_zone_regions_keeps_stored_order():
    regions = zone_regions(SNAPSHOT, "storage")

    assert [region["id"] for region in regions] == [
        "storage-1",
        "storage-2",
        "storage-3",
    ]


def test_zone_regions_is_none_for_unknown_zone_type():
    assert zone_regions(SNAPSHOT, "gone") is None
    assert zone_regions(None, "storage") is None


def test_zone_regions_is_empty_for_a_zone_type_without_regions():
    assert zone_regions(SNAPSHOT, "empty") == []


def test_region_channels_use_the_protocol_map_and_skip_unmapped():
    region = {"id": "r", "electrode_ids": ["c2", "x", "unknown", "c1"]}

    assert region_channels(region, MAPPING) == [4, 5]


def test_detection_channels_are_the_sorted_union():
    regions = zone_regions(SNAPSHOT, "storage")

    assert zone_detection_channels(regions, MAPPING) == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    "detected, criterion, expected",
    [
        ([2], ZoneCriterion.HAS_DROPLET, "storage-1"),
        ([4], ZoneCriterion.HAS_DROPLET, "storage-3"),
        ([3, 5], ZoneCriterion.HAS_DROPLET, "storage-2"),
        ([], ZoneCriterion.HAS_DROPLET, None),
        ([], ZoneCriterion.NO_DROPLET, "storage-1"),
        ([1], ZoneCriterion.NO_DROPLET, "storage-2"),
        ([1, 3], ZoneCriterion.NO_DROPLET, "storage-3"),
        ([1, 3, 5], ZoneCriterion.NO_DROPLET, None),
    ],
)
def test_select_first_region_meeting_the_criterion(detected, criterion, expected):
    regions = zone_regions(SNAPSHOT, "storage")

    assert _ids(select_zone_region(regions, detected, criterion, MAPPING)) == expected


def test_detection_outside_the_zone_is_ignored():
    regions = zone_regions(SNAPSHOT, "storage")

    assert select_zone_region(regions, [99], ZoneCriterion.HAS_DROPLET, MAPPING) is None
    assert _ids(
        select_zone_region(regions, [99], ZoneCriterion.NO_DROPLET, MAPPING)
    ) == ("storage-1")


def test_unmapped_region_never_matches():
    regions = [
        {"id": "dark", "electrode_ids": ["x", "unknown"]},
        {"id": "lit", "electrode_ids": ["a1"]},
    ]

    assert _ids(select_zone_region(regions, [], ZoneCriterion.NO_DROPLET, MAPPING)) == (
        "lit"
    )


def test_unknown_criterion_raises():
    with pytest.raises(ValueError):
        select_zone_region([], [], "Maybe Droplet", MAPPING)
