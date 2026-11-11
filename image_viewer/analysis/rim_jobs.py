# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Off-GUI rim tracer job: follows every ROI's droplet by its bright rim
(rim_tracer) through the frames after the shown one, on a daemon thread
that streams the same ``(kind, payload)`` messages as SamJobRunner's
track — TRACK_FRAME per frame, then TRACK_FINISHED, or AI_FAILED — so
the AI controller drains both runners alike.

A prefetch thread reads and warps each frame while the consumer traces
it. Every frame is traced (the search window assumes consecutive
frames); a user's correction restarts its ROI's chain from that shape,
and an ROI held off a frame is not traced or written there. A trace
outside the size window is rejected: nothing is written and the chain
keeps its last good rim. Traced rims pass through a centred temporal
median, so each frame's shapes are emitted a few frames later, and the
rest on finishing or stopping."""

# Standard library imports.
import itertools
import queue
import threading

# Third-party imports.
import cv2

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance

# Local imports.
from .consts import RIM_GAP_SECONDS, RIM_SEARCH_PX_DEFAULT, RIM_WIDTH_PX_DEFAULT
from .perspective import warp_frame
from .rim_tracer import (
    RimTemporalMedian,
    chain_from_shape,
    rim_ellipse,
    rim_polygon,
    trace_chain,
)
from .sam_detect import Candidate
from .sam_jobs import AI_FAILED, TRACK_FINISHED, TRACK_FRAME

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def candidate_from_rim(centre, radii):
    """The traced rim as a Candidate: its polygon and fitted ellipse."""
    return Candidate(
        polygon=[float(value) for value in rim_polygon(centre, radii).ravel()],
        ellipse=rim_ellipse(centre, radii),
    )


class RimJobRunner(HasTraits):
    """Runs one rim trace at a time off the GUI thread. Starting one
    cancels whichever is running and swaps in a fresh results queue, so
    a superseded trace's stragglers land in a queue nobody drains."""

    #: GUI-drained result queue of (kind, payload) tuples.
    results = Instance(queue.SimpleQueue)

    #: Whether a trace is running: set True at its start and False when
    #: its thread ends, on every path (finished, failed or cancelled).
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
        self.track_running = False

        return self._cancel, self.results

    def track(
        self,
        steps,
        start_shapes,
        min_size,
        max_size,
        perspective=(),
        rim_width_px=RIM_WIDTH_PX_DEFAULT,
        search_px=RIM_SEARCH_PX_DEFAULT,
        start_frame=None,
    ):
        """Trace each ROI across ``steps`` (drift_plan.rim_steps: every
        later frame in series order, each with the shapes the user's
        corrections restart ROIs from and the ROIs held off it), starting
        from ``start_shapes`` = {roi_id: (kind, geometry)}. A trace whose
        size (mean ellipse diameter, px — ``Candidate.size``) falls
        outside ``[min_size, max_size]`` is rejected. Every frame is
        warped by ``perspective`` first (() for none), the space the ROIs
        were drawn in. ``start_frame`` is (path, capture_time) of the
        image the start shapes were drawn on: they are traced there first,
        so the first later frame chains from a rim rather than a shape."""
        cancel, results = self._start_job()
        self.track_running = True
        thread = threading.Thread(
            target=self._run_track,
            args=(
                steps,
                start_shapes,
                min_size,
                max_size,
                perspective,
                rim_width_px,
                search_px,
                start_frame,
                cancel,
                results,
            ),
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def _run_track(
        self,
        steps,
        start_shapes,
        min_size,
        max_size,
        perspective,
        rim_width_px,
        search_px,
        start_frame,
        cancel,
        results,
    ):
        total = len(steps)
        traced = 0
        failure = None
        ready = queue.Queue(maxsize=2)
        prefetcher = threading.Thread(
            target=_prefetch, args=(steps, perspective, cancel, ready), daemon=True
        )
        prefetcher.start()

        segments = itertools.count()
        chains = {
            roi_id: chain_from_shape(kind, geometry, next(segments))
            for roi_id, (kind, geometry) in start_shapes.items()
        }
        smoother = RimTemporalMedian()
        rejected_by_time = {}
        previous_time = None

        def emit(finished_frames):
            for capture_time, rims in finished_frames:
                rejected = rejected_by_time.pop(capture_time, {})
                candidates = {
                    roi_id: candidate_from_rim(centre, radii)
                    for roi_id, (centre, radii) in rims.items()
                }
                candidates.update(dict.fromkeys(rejected))
                results.put(
                    (
                        TRACK_FRAME,
                        {
                            "capture_time": capture_time,
                            "candidates": candidates,
                            "rejected": rejected,
                            "done": traced,
                            "total": total,
                        },
                    )
                )

        try:
            # Not emitted: the shown image keeps the user's shapes. A start
            # shape whose rim is not found there stays the prior.
            if start_frame is not None:
                start_path, previous_time = start_frame
                image = _read_frame(start_path, perspective)

                for chain in chains.values():
                    radii, centre, good = trace_chain(
                        image, chain, search_px, rim_width_px
                    )

                    if good.any() and min_size <= _rim_size(centre, radii) <= max_size:
                        chain.centre, chain.radii = centre, radii
                        chain.from_shape = False

            while not cancel.is_set():
                try:
                    kind, payload = ready.get(timeout=0.2)
                except queue.Empty:
                    continue

                if kind == "end":
                    break

                if kind == "error":
                    raise RuntimeError(payload)

                path, capture_time, seeds, held, image = payload
                after_gap = (
                    previous_time is not None
                    and capture_time - previous_time > RIM_GAP_SECONDS
                )
                previous_time = capture_time

                # A user's correction restarts its chain from that shape;
                # a long gap starts a new median segment for every chain.
                for roi_id, (seed_kind, geometry) in seeds.items():
                    chains[roi_id] = chain_from_shape(
                        seed_kind, geometry, next(segments)
                    )

                if after_gap:
                    for chain in chains.values():
                        chain.segment = next(segments)

                traces = {}
                rejected = {}

                for roi_id, chain in chains.items():
                    if roi_id in held:
                        continue

                    radii, centre, good = trace_chain(
                        image, chain, search_px, rim_width_px, after_gap
                    )
                    size = _rim_size(centre, radii)

                    # An out-of-window rim (a speck ring, a background
                    # edge) counts as nothing found: chaining it would
                    # drag the ROI off the droplet.
                    if not min_size <= size <= max_size:
                        rejected[roi_id] = size
                        logger.info(
                            f"Rim trace {path}: rejected ROI {roi_id}, size "
                            f"{size:.1f} px outside {min_size}-{max_size} px"
                        )
                        continue

                    chain.centre, chain.radii, chain.from_shape = centre, radii, False
                    traces[roi_id] = (chain.segment, centre, radii)
                    logger.debug(
                        f"Rim trace {path}: ROI {roi_id} rim found on "
                        f"{good.mean():.0%} of rays"
                    )

                traced += 1
                rejected_by_time[capture_time] = rejected
                emit(smoother.push(capture_time, traces))

            # Stopped or finished, the frames already traced are kept.
            emit(smoother.flush())
        except Exception as error:
            failure = str(error)
            logger.warning(f"Rim trace failed: {error}")
        finally:
            cancel.set()

            # Unblock the prefetcher if it is waiting on a full queue.
            while True:
                try:
                    ready.get_nowait()
                except queue.Empty:
                    break

            prefetcher.join(timeout=10)

            # cancel (captured at this job's start) is this job's identity
            # token: a newer trace has moved the runner's _cancel on, and
            # clearing track_running here would report that one done.
            if self._cancel is cancel:
                self.track_running = False

            results.put((TRACK_FINISHED, {"frames_done": traced, "total": total}))

            # After the finish message, so its summary does not overwrite
            # the failure on the progress readout.
            if failure is not None:
                results.put((AI_FAILED, {"stage": "rim trace", "error": failure}))


def _prefetch(steps, perspective, cancel, ready):
    """Read and warp each step's frame ahead of the tracer, handing
    ("frame", (path, capture_time, seeds, held, image)) to ``ready``,
    then ("end", None) — or ("error", message) and stop."""
    try:
        for path, capture_time, seeds, held in steps:
            if cancel.is_set():
                return

            frame = (path, capture_time, seeds, held, _read_frame(path, perspective))

            while not cancel.is_set():
                try:
                    ready.put(("frame", frame), timeout=0.2)
                    break
                except queue.Full:
                    continue
    except Exception as error:
        ready.put(("error", str(error)))
        return

    ready.put(("end", None))


def _read_frame(path, perspective):
    """The frame at ``path`` as a grayscale array, warped by
    ``perspective``."""
    image = cv2.imread(path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)

    if image is None:
        raise RuntimeError(f"could not read frame: {path}")

    return warp_frame(image, perspective)


def _rim_size(centre, radii):
    """The rim's size as the size window reads it: the mean diameter of
    its fitted ellipse (``Candidate.size``)."""
    _cx, _cy, rx, ry, _angle = rim_ellipse(centre, radii)

    return rx + ry
