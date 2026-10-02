# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The prototype's shape descriptors, now living in the ROI analysis
package (``image_viewer.analysis.shape_descriptors``) — re-exported so
the runner keeps one implementation with the pane."""

# Microdrop package imports.
from image_viewer.analysis.shape_descriptors import (  # noqa: F401
    DEVIATION_DESCRIPTORS,
    HU_KEYS,
    SCALAR_DESCRIPTORS,
    add_shape_deviation,
    describe_droplet,
)
