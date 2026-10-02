# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Whether two corner quads list their corners in the same order.

Quads pair up by index, so a quad marked clockwise from the top-left in
one image and from the bottom-right (or anticlockwise) in the other maps
the image turned or mirrored. Both quads are [[x, y] * 4] in y-down image
coordinates, as shown to the user."""


def signed_area(quad):
    """Shoelace area: positive for corners listed clockwise (y down)."""
    return (
        sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(quad, quad[1:] + quad[:1]))
        / 2
    )


def top_left_index(quad):
    """Index of the corner nearest the top-left of the quad's bounds."""
    left = min(x for x, _ in quad)
    top = min(y for _, y in quad)

    return min(
        range(len(quad)),
        key=lambda index: (quad[index][0] - left) ** 2 + (quad[index][1] - top) ** 2,
    )


def quads_order_matches(quad_a, quad_b):
    """True when both quads wind the same way from the same corner."""
    same_winding = (signed_area(quad_a) > 0) == (signed_area(quad_b) > 0)

    return same_winding and top_left_index(quad_a) == top_left_index(quad_b)
