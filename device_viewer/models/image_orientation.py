# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""How a raw image is shown: quarter turns, then mirrors.

The display is the raw image turned clockwise ``quarter_turns`` times
(y down), then mirrored left-right and/or top-bottom. Every rotate and
flip the user applies to the DISPLAYED image folds back into that one
canonical form, and points map between raw and display pixels both
ways — so marks placed on the display stay on the same image features
and report raw pixels."""

# Enthought library imports.
from traits.api import Bool, HasTraits, Int


class ImageOrientation(HasTraits):
    #: Clockwise quarter turns applied to the raw image, 0-3.
    quarter_turns = Int(0)

    #: Mirror the turned image left-right.
    flip_horizontal = Bool(False)

    #: Mirror the turned image top-bottom.
    flip_vertical = Bool(False)

    def rotate_clockwise(self):
        """Turn the displayed image a quarter turn clockwise.

        A turn after a mirror equals the opposite mirror after the
        turn, so the two mirrors swap.
        """
        self.trait_set(
            quarter_turns=(self.quarter_turns + 1) % 4,
            flip_horizontal=self.flip_vertical,
            flip_vertical=self.flip_horizontal,
        )

    def flip(self, horizontal):
        """Mirror the displayed image left-right, or top-bottom."""
        if horizontal:
            self.flip_horizontal = not self.flip_horizontal

        else:
            self.flip_vertical = not self.flip_vertical

    def oriented_size(self, size):
        """The displayed (width, height) of a raw image of ``size``."""
        width, height = size

        return (height, width) if self.quarter_turns % 2 else (width, height)

    def map_point(self, point, size):
        """A raw-image point, as [x, y] in the displayed image."""
        width, height = size
        x, y = float(point[0]), float(point[1])

        for _ in range(self.quarter_turns):
            x, y = height - y, x
            width, height = height, width

        if self.flip_horizontal:
            x = width - x

        if self.flip_vertical:
            y = height - y

        return [x, y]

    def unmap_point(self, point, size):
        """A displayed-image point, back as [x, y] in the raw image."""
        width, height = self.oriented_size(size)
        x, y = float(point[0]), float(point[1])

        if self.flip_horizontal:
            x = width - x

        if self.flip_vertical:
            y = height - y

        for _ in range(self.quarter_turns):
            x, y = y, width - x
            width, height = height, width

        return [x, y]
