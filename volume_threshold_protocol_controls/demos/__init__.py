# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Demos / manual test apps for the volume-threshold plugin.

run_volume_threshold_test — a broker-free Qt app that runs a real
ProtocolExecutor over a volume-threshold step and drives a scripted
capacitance timeline to prove the stale-capacitance flush works (a phase
must ignore high readings buffered from the previous phase and advance
only on a genuine crossing).
"""
