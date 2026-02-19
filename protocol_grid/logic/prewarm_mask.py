import numpy as np

def get_prewarm_step_mask(data, prewarm_seconds):
    """
    Calculates a 'System Active' mask that includes:
    1. The Prewarm period (10s before ON).
    2. The ON state itself.
    3. Handles Short OFF gaps (<10s) by keeping the signal True throughout.
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

    # Falling Edges (1 -> 0) - Start of OFF/Idle periods
    off_start_mask = np.zeros(n, dtype=bool)
    off_start_mask[1:] = (states[1:] == 0.0) & (states[:-1] == 1.0)
    off_start_mask[0] = (states[0] == 0.0)
    off_start_indices = np.flatnonzero(off_start_mask)

    offsets = np.zeros(n, dtype=float)
    prewarm_mask = np.zeros(n, dtype=bool)

    # Only process if there are rising edges (ON events)
    if rising_indices.size > 0:
        # Match rising edges to the preceding OFF start
        # This tells us where the current 'Idle' period began
        matched_idx = np.searchsorted(off_start_indices, rising_indices, side='right') - 1
        current_off_starts_indices = off_start_indices[matched_idx]

        # --- 3. Calculate Prewarm Targets ---
        on_times = time_starts[rising_indices]
        off_period_start_times = time_starts[current_off_starts_indices]

        theoretical_targets = on_times - prewarm_seconds

        # --- 4. Apply Clamping (Short Gap Logic) ---
        # If theoretical target is BEFORE the off period started, clamp to OFF start.
        final_target_times = np.maximum(theoretical_targets, off_period_start_times)

        # --- 5. Identify Start Steps & Offsets ---
        # Find which step contains the final_target_time
        start_indices = np.searchsorted(time_ends, final_target_times, side='right')

        # Calculate offset (Time into the step)
        calculated_offsets = final_target_times - time_starts[start_indices]
        offsets[start_indices] = np.maximum(calculated_offsets, 0.0)

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

        True,
        True,
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
            [0.0, 1.0],
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

    not_user_set_video_mask = ~user_set_video_mask

    video_flip_needed_idx = not_user_set_video_mask & prewarm_step_mask
    offset_seconds = offset_seconds * not_user_set_video_mask.astype(int)

    print(video_flip_needed_idx)
    print(offset_seconds)



