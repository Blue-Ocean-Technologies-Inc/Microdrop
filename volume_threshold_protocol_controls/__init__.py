# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Volume-threshold per-step column contribution (#437).

Architecture lives in pluggable_protocol_tree (StepContext events +
RoutesHandler hooks). This plugin ships the column + handler that
subscribes to ELECTRODES_STATE_CHANGE / CAPACITANCE_UPDATED and sets
ctx.phase_advance_event when measured capacitance reaches the per-phase
target. Calibration (full liquid-covered capacitance) and per-channel
electrode areas are read from app_globals, where the device-viewer
models publish them on change.
"""
