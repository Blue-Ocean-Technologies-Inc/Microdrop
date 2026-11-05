# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Contrast-detect autofocus: a coarse-then-fine sweep of the focus
distance, advanced one live frame's sharpness at a time.

Qt-free: the camera controller feeds it each frame's sharpness and moves
the lens to the focus distances it answers with."""

# Third-party imports.
import numpy as np

# Enthought library imports.
from traits.api import Bool, Dict, Enum, Float, HasTraits, Int, List, Union

# Local imports.
from ..consts import (
    AUTOFOCUS_COARSE_STEPS,
    AUTOFOCUS_FINE_STEPS,
    AUTOFOCUS_SAMPLES_PER_POSITION,
    AUTOFOCUS_SETTLE_FRAMES,
)


def laplacian_variance(grey):
    """Sharpness of a 2-D greyscale image: the variance of its 4-neighbour
    Laplacian, which grows with the image's fine detail."""
    image = np.asarray(grey, dtype=np.float32)

    if image.ndim != 2 or min(image.shape) < 3:
        return 0.0

    laplacian = (
        image[:-2, 1:-1]
        + image[2:, 1:-1]
        + image[1:-1, :-2]
        + image[1:-1, 2:]
        - 4.0 * image[1:-1, 1:-1]
    )

    return float(laplacian.var())


class ContrastAutofocus(HasTraits):
    """One autofocus sweep over focus distance 0.0 (near) to 1.0 (far).

    ``start`` answers the first focus distance to move the lens to; each
    ``feed`` of a frame's sharpness answers the next one, None to hold the
    lens, and finally the sharpest distance measured, as ``running`` ends.
    """

    #: Positions of the coarse pass, evenly spaced across the focus range.
    coarse_steps = Int(AUTOFOCUS_COARSE_STEPS)

    #: New positions of the fine pass, evenly spaced between the
    #: neighbours of the best coarse position.
    fine_steps = Int(AUTOFOCUS_FINE_STEPS)

    #: Frames dropped after a lens move before measuring; twice as many
    #: after the long first move of each pass.
    settle_frames = Int(AUTOFOCUS_SETTLE_FRAMES)

    #: Frames whose sharpness is averaged per position.
    samples_per_position = Int(AUTOFOCUS_SAMPLES_PER_POSITION)

    #: A sweep is in progress.
    running = Bool(False)

    #: Focus distance the lens was last sent to.
    target = Union(None, Float)

    #: Mean sharpness per measured focus distance.
    scores = Dict(Float, Float)

    #: Sharpest focus distance of the last finished sweep.
    best_distance = Union(None, Float)

    #: The pass in progress.
    _phase = Enum("coarse", "fine")

    #: Focus distances still to measure in this pass.
    _queue = List(Float)

    #: Frames still to drop at the current position.
    _frames_to_skip = Int(0)

    #: Sharpness samples taken at the current position.
    _samples = List(Float)

    def start(self):
        """Begin a sweep; returns the first focus distance to move to."""
        last = self.coarse_steps - 1

        self.scores = {}
        self.best_distance = None
        self._phase = "coarse"
        self._queue = [step / last for step in range(self.coarse_steps)]
        self.running = True

        return self._move_to_next(self.settle_frames * 2)

    def feed(self, sharpness):
        """Take one frame's sharpness; returns the focus distance to move
        the lens to, or None to hold it there."""

        if not self.running:
            return None

        if self._frames_to_skip > 0:
            self._frames_to_skip -= 1

            return None

        self._samples.append(sharpness)

        if len(self._samples) < self.samples_per_position:
            return None

        self.scores[self.target] = sum(self._samples) / len(self._samples)

        if self._queue:
            return self._move_to_next(self.settle_frames)

        if self._phase == "coarse":
            self._phase = "fine"
            self._queue = self._fine_positions()

            if self._queue:
                return self._move_to_next(self.settle_frames * 2)

        return self._finish()

    def cancel(self):
        """Abandon the sweep in progress; the lens stays where it is."""
        self._queue = []
        self.running = False

    def _move_to_next(self, frames_to_skip):
        self.target = self._queue.pop(0)
        self._frames_to_skip = frames_to_skip
        self._samples = []

        return self.target

    def _fine_positions(self):
        """Unmeasured positions between the best coarse position's
        neighbours, clipped to the focus range."""
        best = max(self.scores, key=self.scores.get)
        coarse_spacing = 1.0 / (self.coarse_steps - 1)
        low = max(0.0, best - coarse_spacing)
        high = min(1.0, best + coarse_spacing)
        intervals = self.fine_steps + 1
        positions = [
            low + (high - low) * step / intervals for step in range(1, intervals)
        ]

        return [position for position in positions if position not in self.scores]

    def _finish(self):
        self.best_distance = max(self.scores, key=self.scores.get)
        self.target = self.best_distance
        self.running = False

        return self.best_distance
