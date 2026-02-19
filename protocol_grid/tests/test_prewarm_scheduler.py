import numpy as np
from protocol_grid.logic.prewarm_mask import get_prewarm_step_mask

def test_short_off_period():
    """
    Scenario: OFF period is 5s (Less than 10s).
    Result: Should be True for the entire OFF period because it's a short gap.
    """
    data = np.array([
        [1.0, 10.0], # 0: ON
        [0.0, 5.0],  # 1: OFF (5s) -> Short gap, stay True.
        [1.0, 10.0]  # 2: ON
    ])

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds=10.0)

    # Expectation: All True.
    # Offsets: 0.0 everywhere.
    expected_mask = np.array([True, True, True])
    expected_offsets = np.array([-10.0, 0.0, 0.0])

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)

def test_long_off_period():
    """
    Scenario: OFF period is 20s (More than 10s).
    Result: First 10s False (Idle), Last 10s True (Prewarm).
    Detailed Timing:
    Step 0: ON [0-10s] -> True
    Step 1: OFF [10-20s] -> Idle (False)
    Step 2: OFF [20-25s] -> Prewarm starts exactly at 20s (10s before ON at 30s) -> True, Offset 0.0
    Step 3: OFF [25-30s] -> True
    Step 4: ON [30-40s] -> True
    """
    data = np.array([
        [1.0, 10.0], # 0
        [0.0, 10.0], # 1: Idle
        [0.0, 5.0],  # 2: Prewarm Start
        [0.0, 5.0],  # 3: Prewarm Cont.
        [1.0, 10.0]  # 4: ON
    ])

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds=10.0)

    expected_mask = np.array([True, False, True, True, True])
    # Offset is 0.0 everywhere because the prewarm start aligns perfectly with the start of Step 2
    expected_offsets = np.array([-10.0, 0.0, 0.0, 0.0, 0.0])

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)

def test_partial_step_offset():
    """
    Scenario: Long OFF, prewarm starts in the middle of a step.
    OFF for 15s. Prewarm 10s.
    Step 0: ON [0-10]
    Step 1: OFF [10-25] -> Duration 15s.
            ON starts at 25s. Prewarm target is 15s.
            Step starts at 10s. Offset = 15s - 10s = 5.0s.
    Step 2: ON [25-35]
    """
    data = np.array([
        [1.0, 10.0],
        [0.0, 15.0],
        [1.0, 10.0]
    ])

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds=10.0)

    expected_mask = np.array([True, True, True])
    # Step 1 has offset 5.0s
    expected_offsets = np.array([-10.0, 5.0, 0.0])

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)

def test_exact_short_boundary():
    """
    Scenario: OFF exactly 9.9s (Short).
    Should be clamped to 0 offset and remain True.
    """
    data = np.array([
        [1.0, 10.0],
        [0.0, 9.9],
        [1.0, 10.0]
    ])

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds=10.0)

    expected_mask = np.array([True, True, True])
    expected_offsets = np.array([-10.0, 0.0, 0.0])

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)

def test_multiple_cycles():
    """
    Cycle 1: Short OFF (5s) -> True (Clamped)
    Cycle 2: Long OFF (20s) -> False then True (Offset calculated)

    Step 0: ON [0-1]
    Step 1: OFF [1-6] (5s gap) -> True
    Step 2: ON [6-7]
    Step 3: OFF [7-27] (20s gap). ON starts at 27. Prewarm target 17.
            Step starts at 7. Offset = 17 - 7 = 10.0s.
    Step 4: ON [27-28]
    """
    data = np.array([
        [1.0, 1.0],
        [0.0, 5.0],
        [1.0, 1.0],
        [0.0, 20.0],
        [1.0, 1.0]
    ])

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds=10.0)

    expected_mask = np.array([True, True, True, True, True])
    # Step 3 is the long gap with the calculated offset
    expected_offsets = np.array([-10.0, 0.0, 0.0, 10.0, 0.0])

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)


def test_negative_offset_first_step():
    """
    Scenario: The first ON event occurs before a full prewarm period can elapse.
    Specifically, the system is OFF for only 5s before turning ON, but the
    prewarm requirement is 10s.

    Expectation: The prewarm calculation should extend before time 0.0, resulting
    in a negative offset (-5.0) for the very first step.
    """
    data = [
        [0, 5],  # Step 0: OFF for 5s (Starts at 0.0)
        [1, 10],  # Step 1: ON for 10s (Starts at 5.0)
    ]
    prewarm_seconds = 10.0

    expected_mask = [True, True]
    expected_offsets = [-5.0, 0.0]

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds)

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)


def test_normal_prewarm_no_negative_offset():
    """
    Scenario: The first ON event happens late enough that the entire prewarm
    period fits within positive time. The system is OFF for 15s, and prewarm is 10s.

    Expectation: The prewarm starts safely within the first step (at 5.0s).
    The offset is positive (5.0), and the negative exception logic is bypassed.
    """
    data = [
        [0, 15],  # Step 0: OFF for 15s (Starts at 0.0)
        [1, 10],  # Step 1: ON for 10s (Starts at 15.0)
    ]
    prewarm_seconds = 10.0

    expected_mask = [True, True]
    expected_offsets = [5.0, 0.0]

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds)

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)


def test_negative_offset_combined_with_short_gap():
    """
    Scenario: Combines the initial negative offset logic with the short-gap clamping
    logic. The first ON starts at 5.0s (needing a -5.0 offset). Later, there is
    a 5s OFF gap between ON states.

    Expectation: The first step gets a negative offset (-5.0). The short OFF gap
    is clamped entirely to its start (offset 0.0) because it is shorter than the
    10s prewarm, keeping the mask True throughout the gap.
    """
    data = [
        [0, 5],  # Step 0: OFF for 5s  (Starts at 0.0)
        [1, 10],  # Step 1: ON for 10s  (Starts at 5.0)
        [0, 5],  # Step 2: OFF for 5s  (Starts at 15.0) - SHORT GAP (< 10s)
        [1, 10],  # Step 3: ON for 10s  (Starts at 20.0)
    ]
    prewarm_seconds = 10.0

    expected_mask = [True, True, True, True]
    expected_offsets = [-5.0, 0.0, 0.0, 0.0]

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds)

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)


def test_start_already_on_with_negative_offset():
    """
    Scenario: The machine starts exactly at time 0.0 in an ON state.

    Expectation: Step 0 is implicitly treated as following an OFF period, resulting
    in a full negative prewarm offset (-10.0). For Step 2 (ON at 30s), a 10s prewarm
    starts exactly midway through Step 1 (at 20s), yielding an offset of 10.0.
    """
    data = [
        [1, 10],  # Step 0: ON for 10s (Starts at 0.0)
        [0, 20],  # Step 1: OFF for 20s (Starts at 10.0, ends at 30.0)
        [1, 10],  # Step 2: ON for 10s (Starts at 30.0)
    ]
    prewarm_seconds = 10.0

    expected_mask = [True, True, True]
    expected_offsets = [-10.0, 10.0, 0.0]

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds)

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)


def test_empty_data():
    """
    Scenario: Data array is completely empty.
    Expectation: Should return empty arrays safely without throwing an exception.
    """
    data = np.empty((0, 2))
    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds=10.0)

    np.testing.assert_array_equal(mask, np.array([], dtype=bool))
    np.testing.assert_allclose(offsets, np.array([], dtype=float))


def test_all_off():
    """
    Scenario: Machine is OFF the entire time. No ON steps exist.
    Expectation: Prewarm mask is False everywhere, offsets are 0.0.
    """
    data = [[0, 10], [0, 20]]
    prewarm_seconds = 10.0

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds)

    expected_mask = [False, False]
    expected_offsets = [0.0, 0.0]

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)


def test_exact_prewarm_match():
    """
    Scenario: Machine is OFF for exactly the duration of the prewarm.
    Expectation: The prewarm starts at exactly 0.0s. Offset is 0.0.
    """
    data = [
        [0, 10],  # Starts at 0.0, ends at 10.0
        [1, 10],  # Starts at 10.0. Prewarm target is 0.0.
    ]
    prewarm_seconds = 10.0

    mask, offsets = get_prewarm_step_mask(data, prewarm_seconds)

    expected_mask = [True, True]
    expected_offsets = [0.0, 0.0]

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)
