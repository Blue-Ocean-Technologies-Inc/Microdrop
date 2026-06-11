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
