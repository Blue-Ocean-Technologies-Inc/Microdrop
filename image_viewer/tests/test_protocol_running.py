# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Running lighter during a protocol: the bounded ROI batch, the view
hold under a draw or edit, and the question heavy work asks first."""

# Standard library imports.
import queue
import threading
import time

# Enthought library imports.
from pyface.api import NO

# Microdrop package imports.
from image_viewer.analysis import protocol_guard, roi_batch
from image_viewer.analysis.consts import PROTOCOL_RUNNING_CONFIRM_MESSAGE
from image_viewer.analysis.roi_batch import (
    BATCH_FINISHED,
    BATCH_RESULT,
    RoiBatchRunner,
)
from image_viewer.analysis.roi_model import RoiAnalysisModel


def _counting_compute(counts, lock):
    """A compute_image_stats stand-in recording how many run at once."""

    def compute(path, rois, *correction):
        with lock:
            counts["running"] += 1
            counts["peak"] = max(counts["peak"], counts["running"])

        time.sleep(0.02)

        with lock:
            counts["running"] -= 1

        return {"path": path, "stats": {}, "error": ""}

    return compute


def test_a_bounded_batch_computes_at_most_that_many_at_once(monkeypatch):
    counts = {"running": 0, "peak": 0}
    monkeypatch.setattr(
        roi_batch, "compute_image_stats", _counting_compute(counts, threading.Lock())
    )
    results = queue.SimpleQueue()
    work = [(f"img{index}.png", {}, ()) for index in range(12)]

    RoiBatchRunner._run(work, threading.Event(), results, max_in_flight=2)
    messages = [results.get_nowait() for _ in range(results.qsize())]

    assert counts["peak"] <= 2
    assert [kind for kind, _payload in messages].count(BATCH_RESULT) == 12
    assert messages[-1][0] == BATCH_FINISHED


def test_a_cancelled_batch_computes_nothing_once_a_slot_frees(monkeypatch):
    computed = []
    monkeypatch.setattr(
        roi_batch, "compute_image_stats", lambda *arguments: computed.append(1)
    )
    cancel = threading.Event()
    cancel.set()

    result = roi_batch._compute_in_slot(
        threading.BoundedSemaphore(1), cancel, "img.png", {}, ()
    )

    assert result is None
    assert computed == []


def test_the_view_is_held_only_under_a_draw_or_edit_during_a_run():
    model = RoiAnalysisModel(interaction_mode="draw_box")

    assert not model.holds_view

    model.protocol_running = True

    assert model.holds_view

    model.interaction_mode = "pan"

    assert not model.holds_view


def test_heavy_work_asks_only_during_a_run(monkeypatch):
    asked = []

    def decline(**kwargs):
        asked.append(kwargs["message"])

        return NO

    monkeypatch.setattr(protocol_guard, "confirm", decline)
    model = RoiAnalysisModel()

    assert protocol_guard.proceed_despite_protocol(model)
    assert asked == []

    model.protocol_running = True

    assert not protocol_guard.proceed_despite_protocol(model)
    assert asked == [PROTOCOL_RUNNING_CONFIRM_MESSAGE]
