# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Point snapping shared by the graphics editors that snap onto a fixed
set of scene points (the camera-alignment quad, the connections editor).
Snap radii are given in VIEW pixels so they feel the same at any zoom;
``scene_view_scale`` converts them to the scene distance the search
takes."""

# Third-party imports.
import numpy as np


def nearest_point_index_within(points, x, y, max_distance):
    """Find the point nearest to (x, y).

    Parameters
    ----------
    points : numpy.ndarray
        The (N, 2) candidate points.
    max_distance : float
        The farthest a point may be, in the same units as ``points``.

    Returns
    -------
    int or None
        The index of the nearest point, or None when even that one is
        farther than ``max_distance``.
    """
    deltas = points - [x, y]
    nearest = int(np.argmin((deltas * deltas).sum(axis=1)))

    if np.hypot(*deltas[nearest]) <= max_distance:
        return nearest

    return None


def scene_view_scale(scene):
    """The zoom (view pixels per scene unit) of the scene's view.

    Assumes the scene has exactly one view (true for the editor canvases,
    which each own their scene) — with several views this reports the
    first one's zoom for all.
    """
    views = scene.views()

    return views[0].transform().m11() if views else 1.0
