"""Constants for the protocol-tree logging subpackage.

App-globals key constants owned by other plugins (channel areas, the device
SVG path, calibration capacitances) are imported from ``device_viewer.consts``
— constants-only reuse, the sanctioned cross-package pattern. Keys/formats
owned by the logger live here.
"""

# Timestamp formats.
TIME_FMT = "%Y-%m-%d %H:%M:%S"        # human-readable metadata (Start/Stop Time)
RUN_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"   # run id + data/report filenames

# app_globals (Redis) bucket of serialised camera captures for the active run.
MEDIA_CAPTURES_KEY = "media_captures"

# app_globals key for the logs-settling preference (seconds). The owning plugin
# (protocol_grid) may mirror its preference here; until then the default below
# is used so the logger stays decoupled from protocol_grid.
LOGS_SETTLING_TIME_S_KEY = "logs_settling_time_s"
DEFAULT_SETTLING_TIME_S = 3.0
