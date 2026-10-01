# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Off-GUI SAM job runner: pick / detect-all / track, each a daemon
thread that streams ``(kind, payload)`` tuples through a thread-safe
queue for the dock pane's drain timer to empty on the GUI thread —
this plugin's established off-GUI pattern (see ``roi_batch.py``).

Track is the interesting one: it ports the PROTO ``droplet_roi``
prototype's ``TrackWorker.run`` pipeline (labelme-derived) without Qt.
A prefetch thread loads + normalizes + encodes each frame that will be
segmented (every ``interval``-th frame, plus always the last — the
skipped frames are simply never emitted, so the consumer's previous
geometry carries forward for free) while the consumer decodes each
ROI's center in a small pool and chains the found center into the
next segmented frame.
"""

# Standard library imports.
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

# Third-party imports.
import cv2

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance

# Local imports.
from .perspective import embedding_id, warp_frame
from .sam_detect import (
    candidate_from_detection,
    normalize_to_uint8,
    suppress_with_votes,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Queue message kinds.
PICK_RESULT = "pick"
DETECT_PROGRESS = "detect_progress"
DETECT_RESULT = "detect"
TRACK_FRAME = "track_frame"
TRACK_FINISHED = "track_finished"
AI_FAILED = "ai_failed"


class SamJobRunner(HasTraits):
    """Runs one SAM job (pick, detect-all, or track) at a time off the
    GUI thread. Starting any job cancels whichever one is running and
    swaps in a fresh results queue, so a superseded job's stragglers
    land in a queue nobody drains anymore."""

    #: GUI-drained result queue of (kind, payload) tuples.
    results = Instance(queue.SimpleQueue)

    #: Whether a track job is currently running -- the GUI reads this
    #: to gate the track button/progress UI. Set True at track start
    #: and False when the track thread ends, on every path (finished,
    #: failed, or cancelled).
    track_running = Bool(False)

    _thread = Instance(object)
    #: threading.Event is unnameable as a Traits type; Instance(object)
    #: is the narrow-not-Any choice for it.
    _cancel = Instance(object)

    def _results_default(self):
        return queue.SimpleQueue()

    def __cancel_default(self):
        return threading.Event()

    def cancel(self):
        self._cancel.set()

    def _start_job(self):
        self.cancel()
        self.results = queue.SimpleQueue()
        self._cancel = threading.Event()
        # Each launcher re-establishes its own state (track() re-sets this
        # True right after calling _start_job); if a pick/detect supersedes
        # a running track, the dying track's identity-guarded finally in
        # _run_track will skip clearing this (its _cancel token no longer
        # matches), so without this it would stay True forever and
        # permanently short-circuit _on_track's toggle guard.
        self.track_running = False
        return self._cancel, self.results

    # -- pick -----------------------------------------------------------

    def pick(self, refiner, image_id, gray_u16, x, y, cache_id=None):
        """One click -> one SAM point prompt -> one Candidate (or
        None). ``cache_id`` keys the encoder's cache when the pixels are
        not the file's own (perspective-warped); ``image_id`` otherwise."""
        _cancel, results = self._start_job()
        thread = threading.Thread(
            target=self._run_pick,
            args=(refiner, image_id, cache_id or image_id, gray_u16, x, y, results),
            daemon=True,
        )
        self._thread = thread
        thread.start()

    @staticmethod
    def _run_pick(refiner, image_id, cache_id, gray_u16, x, y, results):
        try:
            gray_u8 = normalize_to_uint8(gray_u16)
            refiner.prepare(cache_id, gray_u8)
            detection = refiner.segment_point(cache_id, x, y)
            candidate = (
                candidate_from_detection(detection, prompt=[x, y], source="click")
                if detection is not None
                else None
            )
        except Exception as error:
            results.put((AI_FAILED, {"stage": "pick", "error": str(error)}))
            logger.warning(f"SAM pick failed: {error}")
            return
        results.put((PICK_RESULT, {"image_id": image_id, "candidate": candidate}))

    # -- detect-all -------------------------------------------------------

    def detect_all(self, refiner, image_id, gray_u16, capture_time, cache_id=None):
        """Point-grid sweep -> every droplet on this frame (``cache_id``
        as for pick)."""
        _cancel, results = self._start_job()
        thread = threading.Thread(
            target=self._run_detect_all,
            args=(
                refiner,
                image_id,
                cache_id or image_id,
                gray_u16,
                capture_time,
                results,
            ),
            daemon=True,
        )
        self._thread = thread
        thread.start()

    @staticmethod
    def _run_detect_all(refiner, image_id, cache_id, gray_u16, capture_time, results):
        try:
            gray_u8 = normalize_to_uint8(gray_u16)
            refiner.prepare(cache_id, gray_u8)
            triples = refiner.segment_grid(
                cache_id,
                gray_u8.shape,
                progress_cb=lambda done, total: results.put(
                    (DETECT_PROGRESS, {"done": done, "total": total})
                ),
            )
            prompt_by_id = {id(detection): prompt for detection, prompt, _ in triples}
            kept = suppress_with_votes(
                [(detection, votes) for detection, _, votes in triples]
            )
            candidates = [
                candidate
                for detection, votes in kept
                if (
                    candidate := candidate_from_detection(
                        detection, prompt=prompt_by_id[id(detection)], votes=votes
                    )
                )
                is not None
            ]
        except Exception as error:
            results.put((AI_FAILED, {"stage": "detect", "error": str(error)}))
            logger.warning(f"SAM detect failed: {error}")
            return
        results.put(
            (
                DETECT_RESULT,
                {
                    "image_id": image_id,
                    "capture_time": capture_time,
                    "candidates": candidates,
                },
            )
        )

    # -- track ------------------------------------------------------------

    def track(self, refiner, frames, start_geometries, interval, perspective=()):
        """Track each ROI across ``frames`` = [(path_str, capture_time),
        ...] in series order, starting from ``start_geometries`` =
        {roi_id: (cx, cy)}. Only every ``interval``-th frame (plus
        always the final one) is segmented; the rest emit nothing.
        Every frame is warped by ``perspective`` first (() for none), the
        space the ROIs were drawn in."""
        cancel, results = self._start_job()
        self.track_running = True
        thread = threading.Thread(
            target=self._run_track,
            args=(
                refiner,
                frames,
                start_geometries,
                interval,
                perspective,
                cancel,
                results,
            ),
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def _run_track(
        self, refiner, frames, start_geometries, interval, perspective, cancel, results
    ):
        total = len(frames)
        frames_done = 0
        step = max(interval, 1)
        segment_indices = sorted(
            set(range(0, total, step)) | ({total - 1} if total else set())
        )
        segment_frames = [frames[index] for index in segment_indices]
        ready = queue.Queue(maxsize=2)

        def prefetch():
            try:
                for path, capture_time in segment_frames:
                    if cancel.is_set():
                        return
                    image = cv2.imread(path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
                    if image is None:
                        ready.put(("error", f"could not read frame: {path}"))
                        return
                    refiner.prepare(
                        embedding_id(path, perspective),
                        normalize_to_uint8(warp_frame(image, perspective)),
                    )
                    while not cancel.is_set():
                        try:
                            ready.put(("frame", (path, capture_time)), timeout=0.2)
                            break
                        except queue.Full:
                            continue
            except Exception as error:
                ready.put(("error", str(error)))
                return
            ready.put(("end", None))

        prefetcher = threading.Thread(target=prefetch, daemon=True)
        prefetcher.start()
        centers = dict(start_geometries)
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                while not cancel.is_set():
                    try:
                        kind, payload = ready.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if kind == "end":
                        break
                    if kind == "error":
                        results.put((AI_FAILED, {"stage": "track", "error": payload}))
                        logger.warning(f"SAM track failed: {payload}")
                        break
                    path, capture_time = payload
                    roi_ids = list(centers)

                    def segment_one(roi_id):
                        cx, cy = centers[roi_id]
                        return roi_id, refiner.segment_point(
                            embedding_id(path, perspective), cx, cy
                        )

                    detections = dict(pool.map(segment_one, roi_ids))
                    candidates = {}
                    for roi_id, detection in detections.items():
                        candidate = (
                            candidate_from_detection(
                                detection, prompt=list(centers[roi_id])
                            )
                            if detection is not None
                            else None
                        )
                        candidates[roi_id] = candidate
                        if candidate is not None:
                            centers[roi_id] = (
                                candidate.ellipse[0],
                                candidate.ellipse[1],
                            )
                    frames_done += 1
                    results.put(
                        (
                            TRACK_FRAME,
                            {
                                "capture_time": capture_time,
                                "candidates": candidates,
                                # Progress in checked-frame units: done and total
                                # both count only the frames the tracker segments
                                # (every interval-th plus the last).
                                "done": frames_done,
                                "total": len(segment_frames),
                            },
                        )
                    )
        except Exception as error:
            results.put((AI_FAILED, {"stage": "track", "error": str(error)}))
            logger.warning(f"SAM track failed: {error}")
        finally:
            cancel.set()
            while True:  # unblock the prefetcher if it is waiting on a
                # full queue
                try:
                    ready.get_nowait()
                except queue.Empty:
                    break
            prefetcher.join(timeout=10)
            # cancel (captured at this job's start) is this job's identity
            # token: if a newer track has since superseded this one, the
            # runner's shared _cancel has already moved on, and clearing
            # track_running here would wrongly report the newer job done.
            if self._cancel is cancel:
                self.track_running = False
            results.put(
                (
                    TRACK_FINISHED,
                    {
                        "frames_done": frames_done,
                        "total": total,
                    },
                )
            )
