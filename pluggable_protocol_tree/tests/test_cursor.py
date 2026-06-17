from pluggable_protocol_tree.execution.cursor import ExecutionCursor


def test_request_and_clear_seek():
    c = ExecutionCursor()
    c.request_seek([1, 2], 3)
    assert c.resume_target == ((1, 2), 3)
    c.clear_seek()
    assert c.resume_target is None


def test_enter_step_sets_position():
    c = ExecutionCursor()
    c.phase_total = 7
    c.enter_step((0,), 2)
    assert c.step_path == (0,)
    assert c.phase_index == 2
    assert c.phase_total == 0


def test_enter_step_defaults_phase_zero():
    c = ExecutionCursor()
    c.enter_step((1, 0))
    assert c.step_path == (1, 0) and c.phase_index == 0


def test_decision_at_phase_continue_jump_abort():
    c = ExecutionCursor()
    c.step_path = (1,)
    assert c.decision_at_phase(2) == ("continue", 2)   # no target
    c.request_seek((1,), 4)
    assert c.decision_at_phase(0) == ("jump", 4)        # same step
    c.request_seek((2,), 1)
    assert c.decision_at_phase(0) == ("abort", 1)       # different step


def test_frame_for_seek():
    c = ExecutionCursor()
    assert c.frame_for_seek([(0,), (1,)]) is None       # no target
    c.request_seek((1,), 5)
    assert c.frame_for_seek([(0,), (1,), (2,)]) == (1, 5)
