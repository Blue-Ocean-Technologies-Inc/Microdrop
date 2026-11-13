# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Zones tutorial's Zone Target simulator picks the region the app picks.

The page's JavaScript rule is cut out of the tutorial source and run in Node
on the same cases as ``select_zone_region``; skipped where Node is missing.
"""

# Standard library imports.
import json
import re
import shutil
import subprocess
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop package imports.
from zone_protocol_controls.consts import ZoneCriterion
from zone_protocol_controls.zone_selection import select_zone_region

ZONES_SOURCE = (
    Path(__file__).parents[2] / "device_viewer" / "resources" / "zones.src.html"
)
RULE_PATTERN = re.compile(
    r"/\* zone-target-rule:start \*/(.*?)/\* zone-target-rule:end \*/", re.DOTALL
)
NODE = shutil.which("node")

HAS = ZoneCriterion.HAS_DROPLET
NO = ZoneCriterion.NO_DROPLET

#: (regions as [(id, channels)], detected channels, criterion); an empty
#: channel list is a region whose electrodes have no channel number.
CASES = [
    ([("a-1", [1, 2]), ("a-2", [3]), ("a-3", [4])], [1], HAS),
    ([("a-1", [1, 2]), ("a-2", [3]), ("a-3", [4])], [1], NO),
    ([("a-1", [1, 2]), ("a-2", [3]), ("a-3", [4])], [1, 3, 4], NO),
    ([("a-1", [1, 2]), ("a-2", [3]), ("a-3", [4])], [], HAS),
    ([("a-1", [1, 2]), ("a-2", [3]), ("a-3", [4])], [], NO),
    ([("a-1", []), ("a-2", [3]), ("a-3", [4])], [], NO),
    ([("a-1", []), ("a-2", [3])], [3], HAS),
    ([("a-1", [5, 6]), ("a-2", [6, 7])], [6], NO),
    ([("a-1", [5, 6]), ("a-2", [6, 7])], [7], HAS),
    ([], [1], HAS),
]


def _python_pick(regions, detected, criterion):
    """Id the app's own rule picks, built from electrode ids and a channel map."""
    electrode_to_channel = {}
    snapshot_regions = []

    for region_id, channels in regions:
        electrode_ids = [f"{region_id}/{channel}" for channel in channels]
        electrode_to_channel.update(zip(electrode_ids, channels))

        if not channels:
            electrode_ids = [f"{region_id}/unmapped"]
            electrode_to_channel[electrode_ids[0]] = None

        snapshot_regions.append({"id": region_id, "electrode_ids": electrode_ids})

    region = select_zone_region(
        snapshot_regions, detected, criterion, electrode_to_channel
    )

    return region["id"] if region else None


def _page_picks(cases):
    """Ids the page's rule picks for every case, run in Node."""
    rule = RULE_PATTERN.search(ZONES_SOURCE.read_text(encoding="utf-8")).group(1)
    page_cases = [
        [
            [
                {"id": region_id, "channels": channels}
                for region_id, channels in regions
            ],
            detected,
            criterion,
        ]
        for regions, detected, criterion in cases
    ]
    script = (
        f"{rule}\nvar cases = {json.dumps(page_cases)};\n"
        "console.log(JSON.stringify(cases.map(function (c) {\n"
        "  var pick = zoneTargetPick(c[0], c[1], c[2]);\n"
        "  return pick ? pick.id : null;\n"
        "})));\n"
    )

    result = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, check=True
    )

    return json.loads(result.stdout)


@pytest.mark.skipif(NODE is None, reason="Node.js is needed to run the page's rule")
def test_the_page_picks_the_region_the_app_picks():
    expected = [_python_pick(*case) for case in CASES]

    assert _page_picks(CASES) == expected
