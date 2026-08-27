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
TIME_FMT = "%Y-%m-%d %H:%M:%S"        # human-readable metadata (Start/Stop Time)
RUN_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"   # run id + data/report filenames
