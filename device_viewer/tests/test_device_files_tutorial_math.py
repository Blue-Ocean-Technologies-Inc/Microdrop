# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Device Files tutorial's figures compute what the app computes.

The page's JavaScript rules are cut out of the tutorial source and run in
Node on the same cases as the Python they mirror: channel typing, drawing
units, the area scale, the capacitance calibration and volume readout, the
Cl / Cf display format, and Generate Connections. Skipped where Node is
missing.
"""

# Standard library imports.
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import HasTraits, Instance

# Microdrop package imports.
from device_viewer.models.calibration import CalibrationModel
from device_viewer.models.electrodes import Electrodes
from device_viewer.models.volume_estimate import VolumeEstimateModel
from device_viewer.services.electrode_interaction_service import (
    _CHANNEL_REVERT,
    ElectrodeInteractionControllerService,
)
from device_viewer.utils.dmf_utils import SvgUtil
from device_viewer.views.calibration_view.widget import format_value
from device_viewer.views.electrode_view.scale_edit_view import ScaleEditViewController

# Microdrop utils imports.
from microdrop_utils.svg_outline import _mm_converter_func

TUTORIAL_SOURCE = Path(__file__).parents[1] / "resources" / "device_files.src.html"
RULES_PATTERN = re.compile(
    r"/\* device-files-rules:start \*/(.*?)/\* device-files-rules:end \*/", re.DOTALL
)
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="Node.js is needed to run the page's rules"
)

#: (typed text, number of channels).
CHANNEL_TEXT_CASES = [
    ("", 120),
    ("0", 120),
    ("119", 120),
    ("120", 120),
    ("007", 120),
    (" 12 ", 120),
    ("5", 4),
    ("3", 4),
]

UNIT_CASES = [
    (value, unit) for value in (1.0, 7.88, 119.68529) for unit in _mm_converter_func
]

#: (measured area mm², electrodes on, liquid pF, filler pF, live pF, gap µm)
#: over 2 x 2 mm electrodes.
CALIBRATION_CASES = [
    (4.0, 2, 16.0, 4.0, 12.0, 254),
    (3.1, 1, 9.5, 0.0, 5.0, 100),
    (5.0, 3, 6.0, 9.0, 7.0, 254),
    (4.0, 0, 16.0, 4.0, 12.0, 254),
    (2.0, 2, 16.0, 4.0, 0.0, 254),
    (6.5, 4, 30.0, 2.5, 50.0, 180),
]

FORMAT_CASES = [
    24534,
    150000,
    4234.56342,
    125.16854,
    99.55634,
    99.5,
    99.42456,
    98.64685,
    12.5,
    12.1564,
    9.95,
    2.5,
    1.25,
    1.234567,
    1.0,
    0.375,
    0.125,
    0.12345,
    0.08798789,
    0.0100001,
    0.01,
    0.005678,
    0.005,
    0.0001234,
    1e-7,
    1e-8,
]

#: Staggered layouts: rows offset by half a pitch, and the same turned on
#: its side. Generate Connections keeps the first's diagonal pairs
#: (26.6 degrees from vertical) and drops the second's (63.4 degrees).
PITCH, SIZE = 2.06, 2.0
BRICK_ROWS = [
    {
        "id": f"r{row}c{col}",
        "x": col * PITCH + (PITCH / 2 if row % 2 else 0),
        "y": row * PITCH,
        "w": SIZE,
        "h": SIZE,
    }
    for row in range(3)
    for col in range(4)
]
BRICK_COLUMNS = [
    {**rect, "id": rect["id"].replace("r", "q"), "x": rect["y"], "y": rect["x"]}
    for rect in BRICK_ROWS
]


def _run_rules(harness):
    """Run ``harness`` after the page's rules in Node; return its JSON."""
    rules = RULES_PATTERN.search(TUTORIAL_SOURCE.read_text(encoding="utf-8")).group(1)

    result = subprocess.run(
        [NODE, "-e", f"{rules}\nconsole.log(JSON.stringify({harness}));"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    return json.loads(result.stdout)


def _write_device(path, rects):
    """A device SVG in mm with one rectangular electrode per rect."""
    paths = "".join(
        f'<path id="{rect["id"]}" data-channels="{index}" '
        f'd="M {rect["x"]},{rect["y"]} H {rect["x"] + rect["w"]} '
        f'V {rect["y"] + rect["h"]} H {rect["x"]} Z"/>'
        for index, rect in enumerate(rects)
    )

    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'width="40mm" height="40mm">'
        '<g inkscape:label="Device" inkscape:groupmode="layer">'
        f"{paths}</g></svg>",
        encoding="utf-8",
    )

    return path


class _ScalerModel(HasTraits):
    """What the Electrode Area Scaler reads from the main model."""

    electrodes = Instance(Electrodes)


def test_typing_a_channel_follows_the_app():
    service = SimpleNamespace(
        device_viewer_preferences=SimpleNamespace(NUMBER_OF_CHANNELS=0)
    )
    expected = []

    for text, channels in CHANNEL_TEXT_CASES:
        service.device_viewer_preferences.NUMBER_OF_CHANNELS = channels
        value = ElectrodeInteractionControllerService._parse_channel_text(service, text)
        expected.append("revert" if value is _CHANNEL_REVERT else value)

    page = _run_rules(
        f"{json.dumps(CHANNEL_TEXT_CASES)}.map(function (c) "
        "{ return parseChannelText(c[0], c[1]); })"
    )

    assert page == expected


def test_drawing_units_convert_like_the_app():
    expected = [_mm_converter_func[unit](value) for value, unit in UNIT_CASES]

    page = _run_rules(
        f"{json.dumps(UNIT_CASES)}.map(function (c) {{ return toMm(c[0], c[1]); }})"
    )

    assert page == pytest.approx(expected, rel=1e-12)


def test_cl_and_cf_display_like_the_sidebar():
    expected = [
        format_value(value).replace("<sup>2</sup>", "²") for value in FORMAT_CASES
    ]

    page = _run_rules(f"{json.dumps(FORMAT_CASES)}.map(formatCapacitance)")

    assert page == expected


def _app_calibration(device_file, measured, on, liquid_pf, filler_pf, live_pf, gap):
    """Scale, calibrate and read a volume the way the app does."""
    electrodes = Electrodes()
    electrodes.set_electrodes_from_svg_file(str(device_file))

    # Electrode Area Scaler, then the main model's electrode_scale setter.
    electrodes.electrode_right_clicked = electrodes["e0"]
    scaler = ScaleEditViewController(model=_ScalerModel(electrodes=electrodes))
    scaler.real_electrode_area = measured
    electrodes.svg_model.area_scale = scaler.scaling_factor

    calibration = CalibrationModel(electrodes=electrodes)
    electrodes.actuated_channels = set(range(on))

    calibration.last_capacitance = liquid_pf
    calibration.measure_liquid_capacitance()
    calibration.last_capacitance = filler_pf
    calibration.measure_filler_capacitance()

    estimate = VolumeEstimateModel(
        capacitance_pf=live_pf,
        actuated_area_mm2=electrodes.get_activated_electrode_area_mm2(),
        liquid_capacitance_over_area=calibration.liquid_capacitance_over_area,
        filler_capacitance_over_area=calibration.filler_capacitance_over_area,
        gap_um=gap,
    )

    return {
        "factor": scaler.scaling_factor,
        "cl": calibration.liquid_capacitance_over_area,
        "cf": calibration.filler_capacitance_over_area,
        "status": estimate.status_message,
        "covered": estimate.covered_area_mm2,
        "volume": estimate.volume_ul,
        "fill": estimate.fill_fraction,
    }


def test_area_scale_calibration_and_volume_follow_the_app(tmp_path):
    squares = [
        {"id": f"e{index}", "x": index * PITCH, "y": 0, "w": SIZE, "h": SIZE}
        for index in range(4)
    ]
    device_file = _write_device(tmp_path / "squares.svg", squares)

    expected = [_app_calibration(device_file, *case) for case in CALIBRATION_CASES]

    # The figure's arithmetic: n electrodes of the drawn area times the scale.
    page = _run_rules(
        f"{json.dumps(CALIBRATION_CASES)}.map(function (c) {{\n"
        f"  var original = {SIZE} * {SIZE}, factor = scalingFactor(c[0], original);\n"
        "  var area = c[1] * original * factor;\n"
        "  var cl = capacitancePerArea(c[2], area, c[1] > 0);\n"
        "  var cf = capacitancePerArea(c[3], area, c[1] > 0);\n"
        "  var estimate = volumeEstimate(c[4], area, cl, cf, c[5]);\n"
        "  return { factor: factor, cl: cl, cf: cf, status: estimate.status,\n"
        "    covered: estimate.covered, volume: estimate.volume,\n"
        "    fill: estimate.fill };\n"
        "})"
    )

    for app, figure in zip(expected, page):
        assert figure["status"] == app["status"]

        for key in ("factor", "cl", "cf", "covered", "volume", "fill"):
            if app[key] is None:
                assert figure[key] is None
            else:
                assert figure[key] == pytest.approx(app[key], rel=1e-9, abs=1e-12)


@pytest.mark.parametrize(
    "layout_name", ["CONNECTIONS_LAYOUT", "BRICK_ROWS", "BRICK_COLUMNS"]
)
def test_generated_connections_match_the_app(tmp_path, layout_name):
    layouts = {"BRICK_ROWS": BRICK_ROWS, "BRICK_COLUMNS": BRICK_COLUMNS}

    if layout_name in layouts:
        rects = layouts[layout_name]
    else:
        rects = _run_rules(layout_name)

    page = _run_rules(f"generateConnections({json.dumps(rects)})")

    svg_model = SvgUtil(filename=str(_write_device(tmp_path / "layout.svg", rects)))

    assert page == svg_model.neighbours
