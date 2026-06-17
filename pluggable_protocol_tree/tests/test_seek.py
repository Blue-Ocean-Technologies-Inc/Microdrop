from pluggable_protocol_tree.execution.seek import resolve_seek, seek_decision


def test_resolve_seek_finds_frame_index_and_clamps_phase():
    frames = [(0,), (1,), (2,)]
    assert resolve_seek(frames, ((1,), 3)) == (1, 3)
    assert resolve_seek(frames, ((1,), -5)) == (1, 0)


def test_resolve_seek_missing_path_returns_none():
    assert resolve_seek([(0,), (1,)], ((9,), 0)) is None


def test_resolve_seek_none_target_returns_none():
    assert resolve_seek([(0,)], None) is None


def test_seek_decision_continue_when_no_target():
    assert seek_decision(None, (1,), 2) == ("continue", 2)


def test_seek_decision_jump_same_step():
    assert seek_decision(((1,), 4), (1,), 0) == ("jump", 4)


def test_seek_decision_abort_different_step():
    assert seek_decision(((2,), 1), (1,), 0) == ("abort", 1)
