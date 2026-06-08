"""Volume-threshold per-step column contribution (#437).

Architecture lives in pluggable_protocol_tree (StepContext events +
RoutesHandler hooks). This plugin ships the column + handler that
subscribes to ELECTRODES_STATE_CHANGE / CAPACITANCE_UPDATED and sets
ctx.phase_advance_event when measured capacitance reaches the per-phase
target. Calibration (full liquid-covered capacitance) and per-channel
electrode areas are read from app_globals, where the device-viewer
models publish them on change.
"""
