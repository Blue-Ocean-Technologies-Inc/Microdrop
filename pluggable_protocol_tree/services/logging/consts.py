# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Constants for the protocol-tree logging subpackage.

App-globals key constants owned by other plugins (channel areas, the device
SVG path, calibration capacitances) are imported from ``device_viewer.consts``
— constants-only reuse, the sanctioned cross-package pattern. Keys/formats
owned by the logger live here. The logs-settling default is NOT
re-exported here — consumers import DEFAULT_LOGS_SETTLING_SECONDS from
pluggable_protocol_tree.consts directly, under its descriptive name.
"""

# Timestamp formats.
TIME_FMT = "%Y-%m-%d %H:%M:%S"  # human-readable metadata (Start/Stop Time)
RUN_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"  # run id + data/report filenames

# Vacuum permittivity in the units of the dielectric-thickness column, so that
# d_um = eps_r * VACUUM_PERMITTIVITY_PF_UM_PER_MM2 / (C/A in pF/mm^2).
# eps_0 = 8.8541878128e-12 F/m = 8.8541878128 pF/m. With C/A = x pF/mm^2
# = x * 1e6 pF/m^2, d = eps_r * 8.854... / (x * 1e6) m = eps_r * 8.854... / x um.
VACUUM_PERMITTIVITY_PF_UM_PER_MM2 = 8.8541878128

# Data column the ingestion writes and the report footnotes.
DIELECTRIC_THICKNESS_COLUMN = "Dielectric Thickness (um)"
