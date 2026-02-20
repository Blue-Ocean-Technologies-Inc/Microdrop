import numpy as np


def get_prewarm_step_mask(data, prewarm_seconds):
    """
    Calculates a 'System Active' mask that includes:
    1. The Prewarm period (10s before ON).
    2. The ON state itself.
    3. Handles Short OFF gaps (<10s) by keeping the signal True throughout.
    4. Allows a negative offset on the very first step if prewarm pushes before time 0.
    5. Calculates a negative prewarm for Step 0 if the machine starts in an ON state.
    """
    data = np.asarray(data)
    n = len(data)
    if n == 0:
        return np.zeros(0, dtype=bool), np.zeros(0, dtype=float)

    states = data[:, 0]
    durations = data[:, 1]

    # --- 1. Calculate Time Boundaries ---
    time_ends = np.cumsum(durations)
    time_starts = np.empty_like(time_ends)
    time_starts[0] = 0.0
    time_starts[1:] = time_ends[:-1]

    # --- 2. Find Event Indices ---
    # Rising Edges (0 -> 1)
    rising_mask = (states[1:] == 1.0) & (states[:-1] == 0.0)
    rising_indices = np.flatnonzero(rising_mask) + 1

    # If the system starts ON, implicitly treat index 0 as a rising edge
    if states[0] == 1.0:
        rising_indices = np.insert(rising_indices, 0, 0)

    # Falling Edges (1 -> 0) - Start of OFF/Idle periods
    off_start_mask = np.zeros(n, dtype=bool)
    off_start_mask[1:] = (states[1:] == 0.0) & (states[:-1] == 1.0)

    # Always treat time 0.0 as an OFF-start boundary so the first step's
    # clamping/matching logic works whether it started ON or OFF.
    off_start_mask[0] = True
    off_start_indices = np.flatnonzero(off_start_mask)

    offsets = np.zeros(n, dtype=float)
    prewarm_mask = np.zeros(n, dtype=bool)

    # Only process if there are rising edges (ON events)
    if rising_indices.size > 0:
        # Match rising edges to the preceding OFF start
        # This tells us where the current 'Idle' period began
        matched_idx = (
            np.searchsorted(off_start_indices, rising_indices, side="right") - 1
        )
        current_off_starts_indices = off_start_indices[matched_idx]

        # --- 3. Calculate Prewarm Targets ---
        on_times = time_starts[rising_indices]
        off_period_start_times = time_starts[current_off_starts_indices]

        theoretical_targets = on_times - prewarm_seconds

        # --- 4. Apply Clamping (Short Gap Logic) ---
        # If theoretical target is BEFORE the off period started, clamp to OFF start.
        final_target_times = np.maximum(theoretical_targets, off_period_start_times)

        # ALLOW NEGATIVE EXCEPTION: If the very first OFF period starts at time 0
        # and the prewarm goes before time 0, revert the clamp to let it stay negative.
        if current_off_starts_indices[0] == 0 and theoretical_targets[0] < 0:
            final_target_times[0] = theoretical_targets[0]

        # --- 5. Identify Start Steps & Offsets ---
        # Find which step contains the final_target_time
        start_indices = np.searchsorted(time_ends, final_target_times, side="right")

        # Calculate offset (Time into the step)
        calculated_offsets = final_target_times - time_starts[start_indices]

        # Clamp offsets to 0.0 generally so they don't bleed backwards...
        offsets_to_apply = np.maximum(calculated_offsets, 0.0)

        # ...but restore the negative value for the very first event if it was pre-time-0
        if final_target_times[0] < 0:
            offsets_to_apply[0] = calculated_offsets[0]

        offsets[start_indices] = offsets_to_apply

        # --- 6. Generate Prewarm Mask ---
        # Mark from 'start_indices' (inclusive) to 'rising_indices' (exclusive)
        mask_diff = np.zeros(n + 1, dtype=int)
        np.add.at(mask_diff, start_indices, 1)
        np.add.at(mask_diff, rising_indices, -1)
        prewarm_mask = np.cumsum(mask_diff)[:-1].astype(bool)

    # --- 7. Combine with ON State ---
    # Result is True if (Prewarm Active) OR (Machine is ON)
    final_mask = prewarm_mask | (states == 1.0)

    return final_mask, offsets


if __name__ == "__main__":

    user_set_video_mask = np.array([

        False,
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        False
    ])

    video_needed_mask = np.array(
        [
            [1.0, 1.0],
            [0.0, 1.0],
            [0.0, 15.0],
            [1.0, 1.0],
            [1.0, 1.0],
            [0.0, 1.0],
            [1.0, 1.0],
            [0.0, 20.0],
            [0.0, 15.0],
            [1.0, 12.0],
        ]
    )

    prewarm_step_mask, offset_seconds = get_prewarm_step_mask(video_needed_mask, prewarm_seconds=10.0)

    video_flip_needed_idx = user_set_video_mask | prewarm_step_mask
    offset_seconds = offset_seconds

    print(video_flip_needed_idx)
    print(offset_seconds)
