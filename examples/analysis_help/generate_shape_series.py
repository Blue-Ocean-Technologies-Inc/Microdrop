# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Print the help guide's embedded "Shape change over time" series.

Runs the shape-moments prototype's five synthetic droplets
(``examples/shape_moments``) through ``describe_droplet`` and prints, per
droplet, every frame's root-normalised Hu vector (``hu_root``) as
thousandths, trailing zeros dropped. The guide recomputes Shape change
from these vectors in JavaScript, so it can re-baseline when images are
excluded. Paste
the printed ``SHAPE_SERIES`` literal over the one in
``image_viewer/resources/analysis_help.html``. From ``src``::

    pixi run python -m examples.analysis_help.generate_shape_series
"""

# Standard library imports.
import json
import tempfile
from pathlib import Path

# Third-party imports.
import numpy as np

# Microdrop package imports.
from examples.shape_moments.run import measure_series
from examples.shape_moments.synthetic import generate_series
from image_viewer.analysis.shape_descriptors import HU_ROOT_KEY

#: Hu vectors are stored as integer thousandths to keep the page small.
SCALE = 1000


def shape_series():
    """{droplet: [[hu_root in thousandths] per frame]} for the five droplets."""

    with tempfile.TemporaryDirectory() as scratch:
        paths, series = generate_series(Path(scratch) / "frames")
        _frames, results = measure_series(paths, series["rois"])

    vectors = {}

    for name, frames in results.items():
        vectors[name] = [_compact(descriptors[HU_ROOT_KEY]) for descriptors in frames]

    return vectors


def _compact(hu_root):
    """``hu_root`` as integer thousandths without its trailing zeros."""
    values = np.round(np.asarray(hu_root) * SCALE).astype(int).tolist()

    while values and values[-1] == 0:
        values.pop()

    return values


if __name__ == "__main__":
    literal = json.dumps(shape_series(), separators=(",", ":"))
    print(f"var SHAPE_SERIES = {literal};")
