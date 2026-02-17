from protocol_grid.services.utils import determine_run_schedule

def test_empty_sequence():
    """Should return empty list for empty input."""
    assert determine_run_schedule([]) == []

def test_no_state_needed():
    """Events with needs_state=False should be ignored."""
    events = [
        {"start_time": 10, "duration": 5, "needs_state": False},
        {"start_time": 20, "duration": 5, "needs_state": False},
    ]
    assert determine_run_schedule(events) == []

def test_single_event_simple():
    """
    Event starts at 20s, duration 5s.
    Pre-warm 10s.
    Expect: ON at 10s (20-10), OFF at 25s (20+5).
    """
    events = [{"start_time": 20.0, "duration": 5.0, "needs_state": True}]
    schedule = determine_run_schedule(events)
    assert schedule == [(10.0, 25.0)]

def test_single_event_clamped_start():
    """
    Event starts at 5s (less than pre-warm 10s).
    Expect: ON at 0s (max(0, 5-10)), OFF at 10s (5+5).
    """
    events = [{"start_time": 5.0, "duration": 5.0, "needs_state": True}]
    schedule = determine_run_schedule(events)
    assert schedule == [(0.0, 10.0)]

def test_two_events_large_gap():
    """
    Event A: 20s start, 5s dur (Req: 10s -> 25s)
    Event B: 100s start, 5s dur (Req: 90s -> 105s)
    Gap: 90s - 25s = 65s (> 10s max_idle).
    Expect: Two separate blocks.
    """
    events = [
        {"start_time": 20.0, "duration": 5.0, "needs_state": True},
        {"start_time": 100.0, "duration": 5.0, "needs_state": True},
    ]
    schedule = determine_run_schedule(events)
    assert schedule == [(10.0, 25.0), (90.0, 105.0)]

def test_two_events_bridged_gap():
    """
    Event A: 20s start, 5s dur (Req: 10s -> 25s)
    Event B: 40s start, 5s dur (Req: 30s -> 45s)

    Gap Calc:
    Next Start (Pre-warm B) = 30s
    Current End (End A) = 25s
    Gap = 30 - 25 = 5s.

    Since 5s <= 10s (max_idle), they should merge.
    Expect: One block from 10s -> 45s.
    """
    events = [
        {"start_time": 20.0, "duration": 5.0, "needs_state": True},
        {"start_time": 40.0, "duration": 5.0, "needs_state": True},
    ]
    schedule = determine_run_schedule(events)
    assert schedule == [(10.0, 45.0)]

def test_two_events_exact_max_idle_gap():
    """
    Testing the boundary condition (<= vs <).
    Event A: 20s start, 5s dur (Req: 10s -> 25s)
    Event B: 45s start, 5s dur (Req: 35s -> 50s)

    Gap: 35s - 25s = 10s.
    Since 10s <= 10s (max_idle), they should merge.
    Expect: 10s -> 50s.
    """
    events = [
        {"start_time": 20.0, "duration": 5.0, "needs_state": True},
        {"start_time": 45.0, "duration": 5.0, "needs_state": True},
    ]
    schedule = determine_run_schedule(events)
    assert schedule == [(10.0, 50.0)]

def test_overlap_logic():
    """
    Event A: 20s start, 20s dur (Req: 10s -> 40s)
    Event B: 30s start, 5s dur  (Req: 20s -> 35s)

    Event B is completely contained within Event A (time-wise).
    Expect: One block 10s -> 40s.
    """
    events = [
        {"start_time": 20.0, "duration": 20.0, "needs_state": True},
        {"start_time": 30.0, "duration": 5.0, "needs_state": True},
    ]
    schedule = determine_run_schedule(events)
    assert schedule == [(10.0, 40.0)]

def test_mixed_sequence():
    """
    Complex scenario:
    1. A: 10s, dur 5 (Req: 0->15)
    2. B: 20s, dur 5 (Req: 10->25) -> Overlaps A (Gap -5), Merge. New End: 25.
    3. C: 40s, dur 5 (Req: 30->45) -> Gap 30-25=5. Merge. New End: 45.
    4. D: 100s, dur 5 (Req: 90->105) -> Gap 90-45=45. Split.

    Expect: [(0, 45), (90, 105)]
    """
    events = [
        {"start_time": 10.0, "duration": 5.0, "needs_state": True},
        {"start_time": 20.0, "duration": 5.0, "needs_state": True},
        {"start_time": 40.0, "duration": 5.0, "needs_state": True},
        {"start_time": 100.0, "duration": 5.0, "needs_state": True},
    ]
    schedule = determine_run_schedule(events)
    assert schedule == [(0.0, 45.0), (90.0, 105.0)]

def test_unsorted_input():
    """Ensure function handles unsorted input correctly."""
    events = [
        {"start_time": 100.0, "duration": 5.0, "needs_state": True},
        {"start_time": 20.0, "duration": 5.0, "needs_state": True},
    ]
    # Should sort internally and treat as [20, 100] -> Two blocks
    schedule = determine_run_schedule(events)
    assert schedule == [(10.0, 25.0), (90.0, 105.0)]