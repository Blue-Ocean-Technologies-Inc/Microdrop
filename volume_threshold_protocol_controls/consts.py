"""Package-level constants.

PKG / PKG_name derived from __name__ (MicroDrop convention)."""

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

VOLUME_THRESHOLD_COL_ID = "volume_threshold"
VOLUME_THRESHOLD_COL_NAME = "Volume Threshold %"
VOLUME_THRESHOLD_DEFAULT = 0           # percent; 0 disables

# Handler polling interval while waiting for the next phase boundary
# (ELECTRODES_STATE_CHANGE). Short so the handler exits within ~2s of
# Routes finishing — see step_phases_done_event in the spec.
PHASE_POLL_TIMEOUT_S = 2.0

# Polling interval while monitoring CAPACITANCE_UPDATED during a phase.
# Lets the handler re-check stop_event between samples.
CAP_POLL_TIMEOUT_S = 1.0
