# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Device-SVG electrode extraction against the bundled 2x3 device."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest
from shapely.ops import unary_union

# Microdrop utils imports.
from microdrop_utils.svg_outline import device_electrode_polygons, list_device_svgs

DEVICES_DIR = (
    Path(__file__).resolve().parents[2] / "device_viewer" / "resources" / "devices"
)
DEVICE_2X3_SVG = DEVICES_DIR / "2x3device.svg"


def test_2x3_device_electrode_polygons():
    polygons = device_electrode_polygons(DEVICE_2X3_SVG)

    assert len(polygons) == 92
    assert all(polygon.is_valid and polygon.area > 0 for polygon in polygons)

    # Bounds in mm: the Device layer's translate puts the electrodes at
    # the origin.
    bounds = unary_union(polygons).bounds

    assert bounds == pytest.approx((0.0, 0.0, 36.7493, 36.2268), abs=1e-3)


def test_svg_without_device_layer_has_no_polygons(tmp_path):
    svg_file = tmp_path / "empty.svg"
    svg_file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm">'
        '<g id="layer1"><path id="p1" d="M 0,0 H 1 V 1 Z"/></g></svg>'
    )

    assert device_electrode_polygons(svg_file) == []


def test_list_device_svgs(tmp_path):
    for name in ("b.svg", "A.SVG", "notes.txt"):
        (tmp_path / name).write_text("")

    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.svg").write_text("")

    assert [path.name for path in list_device_svgs(tmp_path)] == ["A.SVG", "b.svg"]
    assert list_device_svgs(tmp_path / "missing") == []
    assert list_device_svgs("") == []
