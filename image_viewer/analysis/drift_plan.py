# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drift tracker's plan over the frames after the shown one: which
it segments, and on each, which ROIs it restarts from a shape the user
corrected and which it leaves alone. Pure, so the plan is testable
without SAM; sam_jobs runs it, and rim_jobs runs rim_steps."""

# Local imports.
from .roi_geometry import centre_of


def frame_plan(rois, capture_time):
    """(seeds, held) for the frame captured at ``capture_time``.

    ``seeds`` is {roi_id: (cx, cy)}: the centre of every ROI the user
    gave a shape for that image alone (``local_overrides``) — the
    tracker restarts its chain there, so a correction anchors every
    frame after it. ``held`` is the ROIs the tracker must not segment
    or write on that frame: the ones with such a shape (the user's
    stands) and the ones deleted from it (``applies_at`` False)."""
    seeds = {
        roi.roi_id: centre_of(roi.kind, roi.local_overrides[capture_time])
        for roi in rois
        if capture_time in roi.local_overrides
    }
    held = set(seeds) | {roi.roi_id for roi in rois if not roi.applies_at(capture_time)}

    return seeds, held


def drift_steps(frames, rois, interval):
    """The tracker's steps over ``frames`` = [(path, capture_time), ...]
    (the frames after the shown one, in series order):
    [(path, capture_time, seeds, held), ...] for every ``interval``-th
    frame plus the last — the ones it segments — with ``seeds`` and
    ``held`` as frame_plan's.

    A correction on a frame the tracker does not segment still moves its
    chain: its seed carries to the next segmented frame (a later
    correction wins), where the ROI is segmented from it. An ROI deleted
    from an unsegmented frame needs nothing — nothing is written there
    anyway."""
    total = len(frames)
    step = max(interval, 1)
    segmented = set(range(0, total, step)) | ({total - 1} if total else set())
    steps = []
    carried = {}

    for index, (path, capture_time) in enumerate(frames):
        seeds, held = frame_plan(rois, capture_time)
        carried.update(seeds)

        if index in segmented:
            steps.append((path, capture_time, carried, held))
            carried = {}

    return steps


def rim_steps(frames, rois):
    """The rim tracer's steps over ``frames``: every frame (the tracer
    follows the rim a few px per frame, so it skips none), each as
    drift_steps' but with ``seeds`` as {roi_id: (kind, geometry)} — the
    shape the user gave that image, which the tracer restarts from."""
    by_id = {roi.roi_id: roi for roi in rois}

    return [
        (
            path,
            capture_time,
            {
                roi_id: (
                    by_id[roi_id].kind,
                    by_id[roi_id].local_overrides[capture_time],
                )
                for roi_id in seeds
            },
            held,
        )
        for path, capture_time, seeds, held in drift_steps(frames, rois, 1)
    ]
