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


def test_resolve_seek_uses_explicit_frame_for_repetition():
    # Path (1,) appears at frames 1 and 3 (two reps); target_frame picks one.
    frames = [(0,), (1,), (2,), (1,)]
    assert resolve_seek(frames, ((1,), 0), target_frame=3) == (3, 0)
    assert resolve_seek(frames, ((1,), 0)) == (1, 0)   # first match without it


def test_resolve_seek_out_of_range_frame_returns_none():
    assert resolve_seek([(0,), (1,)], ((1,), 0), target_frame=9) is None


def test_seek_decision_aborts_for_different_repetition_frame():
    # Step-rep seek: same path, but a different frame -> abort to re-enter it.
    assert seek_decision(((1,), 0), (1,), 2,
                         target_frame=5, current_frame_index=3) == ("abort", 0)
    # Same frame -> normal same-path phase jump.
    assert seek_decision(((1,), 4), (1,), 0,
                         target_frame=3, current_frame_index=3) == ("jump", 4)
