# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""ContrastAutofocus driven by synthetic sharpness curves, and the
Laplacian sharpness measure."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np
import pytest

# Microdrop package imports.
from device_viewer.models.autofocus import ContrastAutofocus, laplacian_variance


def _peak(centre, width=0.1):
    return lambda distance: 100.0 * math.exp(-(((distance - centre) / width) ** 2))


def _sweep(autofocus, sharpness_at, max_frames=1000):
    """Run a whole sweep, one frame per feed; returns the lens moves."""
    moves = [autofocus.start()]

    for _ in range(max_frames):
        if not autofocus.running:
            break

        distance = autofocus.feed(sharpness_at(moves[-1]))

        if distance is not None:
            moves.append(distance)

    return moves


@pytest.mark.parametrize("centre", [0.0, 0.37, 0.5, 0.93, 1.0])
def test_sweep_ends_on_the_sharpest_distance(centre):
    autofocus = ContrastAutofocus()

    moves = _sweep(autofocus, _peak(centre))

    assert not autofocus.running
    assert autofocus.best_distance == pytest.approx(centre, abs=0.02)
    assert moves[-1] == autofocus.best_distance


def test_sweep_measures_the_coarse_then_the_fine_positions():
    autofocus = ContrastAutofocus(coarse_steps=12, fine_steps=8)

    moves = _sweep(autofocus, _peak(0.47))

    coarse = moves[:12]
    fine = moves[12:20]
    spacing = 1 / 11

    assert coarse == pytest.approx([step / 11 for step in range(12)])
    assert len(autofocus.scores) == 20
    assert all(abs(position - 5 / 11) < spacing for position in fine)


def test_each_position_waits_out_the_settling_frames():
    autofocus = ContrastAutofocus(settle_frames=4, samples_per_position=2)
    first = autofocus.start()

    # The first move is long: twice the settling frames, then two samples.
    answers = [autofocus.feed(1.0) for _ in range(10)]

    assert answers[:9] == [None] * 9
    assert answers[9] == pytest.approx(1 / 11)
    assert autofocus.scores == {first: 1.0}


def test_samples_are_averaged_per_position():
    autofocus = ContrastAutofocus(settle_frames=0, samples_per_position=2)
    first = autofocus.start()

    autofocus.feed(2.0)
    autofocus.feed(4.0)

    assert autofocus.scores[first] == 3.0


def test_cancel_stops_the_sweep():
    autofocus = ContrastAutofocus(settle_frames=0)
    autofocus.start()
    autofocus.feed(1.0)

    autofocus.cancel()

    assert not autofocus.running
    assert autofocus.feed(1.0) is None
    assert autofocus.best_distance is None


def test_laplacian_variance_ranks_detail_over_blur():
    checkerboard = (np.indices((32, 32)).sum(axis=0) % 2 * 255).astype(np.uint8)
    blurred = np.full((32, 32), 128, np.uint8)

    assert laplacian_variance(checkerboard) > laplacian_variance(blurred) == 0.0
    assert laplacian_variance(np.zeros((2, 2))) == 0.0
