# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The rim tracer: finding a bright rim, following it from frame to
frame, the streaming temporal median, and the runner's message
protocol."""

# Standard library imports.
import queue
import threading

# Third-party imports.
import cv2
import numpy as np

# Microdrop package imports.
from image_viewer.analysis import rim_jobs
from image_viewer.analysis.consts import RIM_GAP_SEARCH_PX, RIM_RAYS
from image_viewer.analysis.rim_tracer import (
    RimTemporalMedian,
    chain_from_shape,
    find_rim,
    rim_points,
    trace_chain,
)
from image_viewer.analysis.sam_jobs import TRACK_FINISHED, TRACK_FRAME

RIM_RADIUS = 150
SPECKS = [(100, 100), (500, 480), (300, 470), (470, 300)]


def _frame(rims, seed=0):
    """A 600 x 600 uint16 frame: background 40, a 5 px rim (2000) per
    (cx, cy, radius) in ``rims``, noise and a few bright specks."""
    image = np.full((600, 600), 40.0)

    for cx, cy, radius in rims:
        cv2.circle(image, (cx, cy), radius, 2000, thickness=5, lineType=cv2.LINE_AA)

    image += np.random.default_rng(seed).normal(0.0, 15.0, image.shape)

    for x, y in SPECKS:
        cv2.circle(image, (x, y), 3, 3000, -1)

    return np.clip(image, 0, 65535).astype(np.uint16)


def _rim_error(centre, radii, true_centre):
    """Each ray's distance from the true rim, px."""
    points = rim_points(centre, radii)

    return (
        np.hypot(points[:, 0] - true_centre[0], points[:, 1] - true_centre[1])
        - RIM_RADIUS
    )


def test_find_rim_recovers_the_rim_from_a_prior_off_it():
    image = _frame([(300, 300, RIM_RADIUS)])

    radii, centre, good = find_rim(
        image, (300.0, 300.0), np.full(RIM_RAYS, 160.0), RIM_GAP_SEARCH_PX, 5
    )

    assert np.mean(np.abs(_rim_error(centre, radii, (300, 300))) <= 1.0) >= 0.95
    assert good.mean() >= 0.95


def test_the_chain_follows_a_moving_droplet():
    chain = chain_from_shape("ellipse", [300.0, 300.0, 160.0, 160.0, 0.0], 0)

    for index in range(3):
        true_centre = (300 + 2 * index, 300)
        image = _frame([(*true_centre, RIM_RADIUS)], seed=index)

        radii, centre, _good = trace_chain(image, chain, 3, 5)
        chain.centre, chain.radii, chain.from_shape = centre, radii, False

        assert np.hypot(centre[0] - true_centre[0], centre[1] - true_centre[1]) < 0.5
        assert np.mean(np.abs(_rim_error(centre, radii, true_centre)) <= 1.0) >= 0.95


def _trace(cx, radius, segment=0):
    return segment, (float(cx), 0.0), np.full(RIM_RAYS, float(radius))


def test_the_streaming_median_emits_each_frame_once_in_order():
    smoother = RimTemporalMedian(window=7)
    emitted = []

    for index in range(10):
        ready = smoother.push(index, {"a": _trace(0, 100 + index)})

        # A frame is final once three more have arrived.
        assert len(ready) == (1 if index >= 3 else 0)

        emitted += ready

    emitted += smoother.flush()

    assert [key for key, _rims in emitted] == list(range(10))

    # Frame 5's median over frames 2-8 is frame 5's own radius.
    _centre, radii = emitted[5][1]["a"]
    assert np.allclose(radii, 105.0)


def test_the_streaming_median_removes_a_hop_but_not_across_segments():
    smoother = RimTemporalMedian(window=3)
    frames = [
        {"a": _trace(0, 100)},
        {"a": _trace(0, 130)},  # a one-frame hop onto another ridge
        {"a": _trace(0, 100)},
        {"a": _trace(0, 100)},
        {"a": _trace(0, 200, segment=1)},  # a restart: never mixed in
    ]
    emitted = []

    for index, traces in enumerate(frames):
        emitted += smoother.push(index, traces)

    emitted += smoother.flush()
    radii = {key: rims["a"][1] for key, rims in emitted}

    assert np.allclose(radii[1], 100.0)
    assert np.allclose(radii[3], 100.0)
    assert np.allclose(radii[4], 200.0)


def _frames_on_disk(monkeypatch, frames):
    monkeypatch.setattr(rim_jobs.cv2, "imread", lambda path, flags: frames[path])


def test_the_runner_streams_track_frames_and_rejects_by_size(monkeypatch):
    # Droplet a drifts 2 px a frame; b is too small for the size window.
    frames = {
        f"f{index}.png": _frame([(200 + 2 * index, 300, 120), (480, 300, 50)], index)
        for index in range(4)
    }
    _frames_on_disk(monkeypatch, frames)
    steps = [
        ("f1.png", 1.0, {}, set()),
        ("f2.png", 2.0, {}, set()),
        ("f3.png", 3.0, {}, {"a"}),  # a is held off f3: nothing written
    ]
    starts = {
        "a": ("ellipse", [200.0, 300.0, 125.0, 125.0, 0.0]),
        "b": ("ellipse", [480.0, 300.0, 50.0, 50.0, 0.0]),
    }
    results = queue.SimpleQueue()

    rim_jobs.RimJobRunner()._run_track(
        steps, starts, 200, 300, (), 5, 3, ("f0.png", 0.0), threading.Event(), results
    )

    messages = []

    while not results.empty():
        messages.append(results.get())

    frames_out = [payload for kind, payload in messages if kind == TRACK_FRAME]

    assert [payload["capture_time"] for payload in frames_out] == [1.0, 2.0, 3.0]
    assert [payload["done"] for payload in frames_out] == [3, 3, 3]
    assert all(payload["total"] == 3 for payload in frames_out)

    for payload in frames_out:
        assert payload["candidates"]["b"] is None
        assert 90.0 < payload["rejected"]["b"] < 110.0

    assert sorted(frames_out[2]["candidates"]) == ["b"]

    # a is traced at x = 202 and 204 on f1 and f2: the temporal median
    # (only those two, a being held off f3) puts both at 203.
    for payload in frames_out[:2]:
        candidate = payload["candidates"]["a"]

        assert abs(candidate.ellipse[0] - 203.0) < 0.5
        assert abs(candidate.size - 240.0) < 3.0
        assert len(candidate.polygon) % 2 == 0

    assert messages[-1] == (TRACK_FINISHED, {"frames_done": 3, "total": 3})
