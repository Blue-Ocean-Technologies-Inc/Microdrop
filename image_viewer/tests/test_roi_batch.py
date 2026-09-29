# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Batch runner end-to-end on tiny synthetic images (real process pool)."""

# Standard library imports.
import queue
import time

# Third-party imports.
import cv2
import numpy as np

# Microdrop package imports.
from image_viewer.analysis.roi_batch import (
    BATCH_FINISHED,
    BATCH_RESULT,
    INSTANT_RESULT,
    RoiBatchRunner,
)


def _drain_until(results, wanted_kind, timeout_s=60.0):
    messages = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            message = results.get(timeout=0.5)
        except queue.Empty:
            continue
        messages.append(message)
        if message[0] == wanted_kind:
            return messages
    raise AssertionError(f"no {wanted_kind} within {timeout_s}s: {messages}")


def _write_image(path, value):
    cv2.imwrite(str(path), np.full((20, 20), value, dtype=np.uint16))


def test_batch_computes_all_images_and_finishes(tmp_path):
    paths = []
    for index, value in enumerate((100, 200)):
        path = tmp_path / f"img{index}_raw.png"
        _write_image(path, value)
        paths.append(str(path))
    rois = {"r1": ("box", (2.0, 2.0, 10.0, 10.0))}
    runner = RoiBatchRunner()
    runner.start([(path, rois, (2, 4, 0)) for path in paths])
    messages = _drain_until(runner.results, BATCH_FINISHED)
    payloads = [payload for kind, payload in messages if kind == BATCH_RESULT]
    assert sorted(payload["stats"]["r1"]["mean"] for payload in payloads) == [
        100.0,
        200.0,
    ]


def test_compute_single_reports_on_queue(tmp_path):
    path = tmp_path / "one_raw.png"
    _write_image(path, 300)
    runner = RoiBatchRunner()
    runner.compute_single(
        str(path), {"r1": ("ellipse", (10.0, 10.0, 4.0, 4.0, 0.0))}, (2, 4, 0)
    )
    messages = _drain_until(runner.results, INSTANT_RESULT, timeout_s=15.0)
    kind, payload = messages[-1]
    assert payload["stats"]["r1"]["mean"] == 300.0
