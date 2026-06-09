"""Demos / manual test apps for the volume-threshold plugin.

run_volume_threshold_test — a broker-free Qt app that runs a real
ProtocolExecutor over a volume-threshold step and drives a scripted
capacitance timeline to prove the stale-capacitance flush works (a phase
must ignore high readings buffered from the previous phase and advance
only on a genuine crossing).
"""
