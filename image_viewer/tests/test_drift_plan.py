# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drift tracker's plan: segmented frames, restarts from the user's
corrections, and the ROIs held off a frame."""

# Standard library imports.
import queue
import threading
from types import SimpleNamespace

# Third-party imports.
import numpy as np

# Microdrop package imports.
from image_viewer.analysis import sam_jobs
from image_viewer.analysis.drift_plan import drift_steps, frame_plan
from image_viewer.analysis.roi_model import Roi

FRAMES = [(f"f{index}.png", float(index)) for index in range(1, 8)]


def _roi(**traits):
    return Roi(kind="ellipse", geometry=[10.0, 10.0, 3.0, 3.0, 0.0], **traits)


def test_every_interval_th_frame_and_the_last_are_segmented():
    steps = drift_steps(FRAMES, [_roi()], 3)

    assert [capture_time for _path, capture_time, _seeds, _held in steps] == [
        1.0,
        4.0,
        7.0,
    ]
    assert all(seeds == {} and held == set() for *_rest, seeds, held in steps)


def test_a_correction_restarts_the_chain_and_holds_its_own_frame():
    roi = _roi(local_overrides={4.0: [40.0, 41.0, 3.0, 3.0, 0.0]})

    seeds, held = frame_plan([roi], 4.0)

    assert seeds == {roi.roi_id: (40.0, 41.0)}
    assert held == {roi.roi_id}

    steps = drift_steps(FRAMES, [roi], 3)

    assert steps[1][2:] == ({roi.roi_id: (40.0, 41.0)}, {roi.roi_id})
    assert steps[2][2:] == ({}, set())


def test_a_correction_between_segmented_frames_seeds_the_next_one():
    roi = _roi(
        local_overrides={
            2.0: [20.0, 20.0, 3.0, 3.0, 0.0],
            3.0: [30.0, 31.0, 3.0, 3.0, 0.0],
        }
    )

    steps = drift_steps(FRAMES, [roi], 3)

    # Segmented from the later correction, not held: frame 4 is the
    # tracker's to write.
    assert steps[1][1] == 4.0
    assert steps[1][2:] == ({roi.roi_id: (30.0, 31.0)}, set())


def test_an_roi_deleted_from_a_frame_is_held_off_it():
    deleted_here = _roi(absent_at=[4.0])
    deleted_onward = _roi(absent_from=7.0)
    kept = _roi()

    steps = drift_steps(FRAMES, [deleted_here, deleted_onward, kept], 3)

    assert steps[0][3] == set()
    assert steps[1][3] == {deleted_here.roi_id}
    assert steps[2][3] == {deleted_onward.roi_id}


class _FakeRefiner:
    """Records each segment_point prompt; "finds" the droplet one pixel
    right of wherever it is prompted."""

    def __init__(self):
        self.prompts = []

    def prepare(self, image_id, image):
        pass

    def segment_point(self, image_id, cx, cy):
        self.prompts.append((image_id, cx, cy))

        return (cx + 1.0, cy)


def test_the_runner_restarts_from_seeds_and_leaves_held_rois_alone(monkeypatch):
    monkeypatch.setattr(
        sam_jobs.cv2, "imread", lambda path, flags: np.zeros((4, 4), np.uint16)
    )
    monkeypatch.setattr(sam_jobs, "embedding_id", lambda path, perspective: path)
    monkeypatch.setattr(
        sam_jobs,
        "candidate_from_detection",
        lambda detection, prompt: SimpleNamespace(ellipse=detection),
    )
    refiner = _FakeRefiner()
    results = queue.Queue()
    steps = [
        ("f1.png", 1.0, {}, set()),
        ("f2.png", 2.0, {"a": (50.0, 50.0)}, {"a"}),
        ("f3.png", 3.0, {}, {"b"}),
    ]
    starts = {"a": (10.0, 10.0), "b": (20.0, 20.0)}

    sam_jobs.SamJobRunner()._run_track(
        refiner, steps, starts, (), threading.Event(), results
    )

    assert sorted(refiner.prompts) == [
        ("f1.png", 10.0, 10.0),
        ("f1.png", 20.0, 20.0),
        ("f2.png", 21.0, 20.0),  # a is held on f2: only b is segmented
        ("f3.png", 50.0, 50.0),  # a restarts from its correction
    ]

    frames = []

    while not results.empty():
        kind, payload = results.get()

        if kind == sam_jobs.TRACK_FRAME:
            frames.append((payload["capture_time"], sorted(payload["candidates"])))

    assert frames == [(1.0, ["a", "b"]), (2.0, ["b"]), (3.0, ["a"])]
