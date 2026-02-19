import numpy as np
import pytest
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
    expected_offsets = np.array([0.0, 0.0, 0.0])

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
    expected_offsets = np.array([0.0, 0.0, 0.0, 0.0, 0.0])

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
    expected_offsets = np.array([0.0, 5.0, 0.0])

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
    expected_offsets = np.array([0.0, 0.0, 0.0])

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
    expected_offsets = np.array([0.0, 0.0, 0.0, 10.0, 0.0])

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_allclose(offsets, expected_offsets)