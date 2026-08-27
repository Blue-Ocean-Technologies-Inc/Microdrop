# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure-logic seams of the dynamic duration loop (#477).

Only ``dyn_resume_start`` is unit-tested here; the threaded loop in
``_run_dynamic_duration_loop`` is verified manually (it runs on a worker
thread under volume-threshold).
"""

from pluggable_protocol_tree.builtins.routes_column import dyn_resume_start


def test_dyn_resume_start_normal_phase():
    assert dyn_resume_start(0, 4) == (0, False)
    assert dyn_resume_start(2, 4) == (2, False)


def test_dyn_resume_start_idle_cell():
    # cursor index == cycle_len -> idle cell
    assert dyn_resume_start(4, 4) == (0, True)


def test_dyn_resume_start_clamps_out_of_range():
    assert dyn_resume_start(9, 4) == (0, True)   # >= cycle_len clamps to idle
    assert dyn_resume_start(-1, 4) == (0, False)
