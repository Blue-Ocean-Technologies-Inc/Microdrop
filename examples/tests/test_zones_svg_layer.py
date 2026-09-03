# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Round-trip of electrode zone regions through the device SVG."""

# Standard library imports.
import os
import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

# Third-party imports.
import pytest


@pytest.fixture
def svg_copy():
    from .common import TEST_PATH

    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.copy(f"{TEST_PATH}{os.sep}device_svg_files{os.sep}2x3device.svg", tmpdir)
        yield Path(tmpdir) / "2x3device.svg"


@pytest.fixture
def SvgUtil():
    from device_viewer.utils.dmf_utils import SvgUtil

    return SvgUtil


def test_fresh_device_has_no_zone_records(svg_copy, SvgUtil):
    assert SvgUtil(filename=svg_copy).zone_records == []


def test_zone_layer_round_trip(svg_copy, SvgUtil):
    from device_viewer.consts import ZONES_SVG_LAYER_LABEL

    svg = SvgUtil(filename=svg_copy)
    ids = sorted(svg.polygons)
    records = [
        {
            "id": "heating-1",
            "zone_id": "heating",
            "zone_name": "heating",
            "zone_color": "#f5e050",
            "visible": True,
            "electrode_ids": ids[:2],
        },
        {
            "id": "mixing-3",
            "zone_id": "mixing",
            "zone_name": "mix",
            "zone_color": "#e06666",
            "visible": False,
            "electrode_ids": ids[2:3],
        },
    ]
    svg.zone_records = records
    saved = svg_copy.with_name("saved.svg")
    svg.save_to_file(saved, {})

    labels = [
        element.get("{http://www.inkscape.org/namespaces/inkscape}label")
        for element in ET.parse(saved).getroot()
    ]
    assert labels.count(ZONES_SVG_LAYER_LABEL) == 1
    assert SvgUtil(filename=saved).zone_records == records


def test_save_rewrites_zone_layer_without_duplicates(svg_copy, SvgUtil):
    from device_viewer.consts import ZONES_SVG_LAYER_LABEL

    svg = SvgUtil(filename=svg_copy)
    ids = sorted(svg.polygons)
    svg.zone_records = [
        {
            "id": "heating-1",
            "zone_id": "heating",
            "zone_name": "heating",
            "zone_color": "#f5e050",
            "visible": True,
            "electrode_ids": ids[:1],
        }
    ]
    first = svg_copy.with_name("first.svg")
    svg.save_to_file(first, {})
    reloaded = SvgUtil(filename=first)
    reloaded.zone_records = []
    second = svg_copy.with_name("second.svg")
    reloaded.save_to_file(second, {})
    labels = [
        element.get("{http://www.inkscape.org/namespaces/inkscape}label")
        for element in ET.parse(second).getroot()
    ]
    assert ZONES_SVG_LAYER_LABEL not in labels
    assert SvgUtil(filename=second).zone_records == []
