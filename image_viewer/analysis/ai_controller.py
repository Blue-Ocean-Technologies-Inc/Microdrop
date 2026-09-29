# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller for the AI (SAM) ROI tools: reacts to the pick/detect/track
toolbuttons and canvas events, gates every launch on the model being
downloaded, and drains the off-GUI job runner's results into the shared
analysis model. All observers run on the GUI thread; the only off-thread
work is inside SamJobRunner.

Sanctioned exception to the analysis package's Qt-free rule: the model
gate below (``_ensure_model_ready``) deliberately imports
``download_ai_model`` from ``..sam_download``, a Qt view-layer module,
because the blocking cancellable download progress dialog lives there."""

# Standard library imports.
import queue

# Enthought library imports.
from traits.api import Bool, Either, Float, HasTraits, Instance, Str, observe

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import information

# Local imports.
from ..discovery import capture_timestamp
from ..model import ImageViewerModel
from ..sam_download import download_ai_model, model_is_cached
from .perspective import embedding_id, warp_frame
from .roi_geometry import centre_of
from .roi_model import RoiAnalysisModel
from .sam_detect import (
    DEFAULT_AI_MODEL,
    SamRefiner,
    gpu_encoder_available,
    sam_available,
    set_gpu_encoder_enabled,
)
from .sam_jobs import (
    AI_FAILED,
    DETECT_PROGRESS,
    DETECT_RESULT,
    PICK_RESULT,
    TRACK_FINISHED,
    TRACK_FRAME,
    SamJobRunner,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class AiRoiController(HasTraits):
    """Glue between the viewer model (image + preferences), the analysis
    model (AI toolbar/candidate state), and the SAM job runner."""

    viewer_model = Instance(ImageViewerModel)
    analysis_model = Instance(RoiAnalysisModel)
    runner = Instance(SamJobRunner, ())

    #: The active refiner, rebuilt whenever the preferred model changes.
    refiner = Either(None, Instance(SamRefiner))

    #: The preference's model name as of the last successful switch, for
    #: reverting a change to an uncached model that could not download.
    _last_ai_model = Str()

    #: Guards the preference observer against reacting to its own revert.
    _reverting_model = Bool(False)

    #: Capture time of the frame the last Detect-all pass ran on — the
    #: anchor accepted candidates (and immediate pick accepts) attach to.
    _detect_anchor = Float(0.0)

    @property
    def session(self):
        return self.analysis_model.session

    # ------------------------------------------------------------------ #
    # Setup                                                                #
    # ------------------------------------------------------------------ #
    @observe("viewer_model, analysis_model")
    def _on_models_ready(self, event):
        """Both models are constructor arguments, and traits assigns
        them one at a time — so this watches both and acts when the
        second arrives, whichever order the caller passed them in."""
        if self.viewer_model is None or self.analysis_model is None:
            return
        self.analysis_model.ai_available = sam_available()
        self._last_ai_model = self.viewer_model.preferences.ai_model
        set_gpu_encoder_enabled(self.viewer_model.preferences.ai_use_gpu)

    # ------------------------------------------------------------------ #
    # Model gate + refiner lifecycle                                       #
    # ------------------------------------------------------------------ #
    def _ensure_model_ready(self):
        """Whether the preferred SAM model is available for use, prompting
        a download (blocking, cancellable dialog) if it is not yet cached.
        False aborts the calling launcher with a progress-text message."""
        if not sam_available():
            self.analysis_model.progress_text = "AI model not available"
            return False
        name = self.viewer_model.preferences.ai_model
        if model_is_cached(name) or download_ai_model(name):
            return True
        self.analysis_model.progress_text = "AI model not available"
        return False

    def _refiner_for_current_model(self):
        name = self.viewer_model.preferences.ai_model
        if self.refiner is None or self.refiner.model_name != name:
            self.refiner = SamRefiner(model_name=name)
        return self.refiner

    @observe("viewer_model:preferences:ai_model")
    def _on_preferred_model_changed(self, event):
        if self._reverting_model:
            return
        new = event.new
        if not sam_available():
            # No download is possible without the stack, but the AI tools
            # are disabled in the UI in that case anyway — just track it.
            self._last_ai_model = new
            return
        if model_is_cached(new) or download_ai_model(new):
            self._last_ai_model = new
            self.refiner = None  # rebuilt on next use
            return
        self._reverting_model = True
        self.viewer_model.preferences.ai_model = self._last_ai_model or DEFAULT_AI_MODEL
        self._reverting_model = False

    @observe("viewer_model:preferences:ai_use_gpu")
    def _on_use_gpu_changed(self, event):
        set_gpu_encoder_enabled(event.new)
        # Encoder sessions pick their provider when built: drop the
        # refiner so the next use rebuilds with the new setting.
        self.refiner = None
        if event.new and sam_available() and not gpu_encoder_available():
            information(
                message="GPU encoding is not available: the installed "
                "onnxruntime has no DirectML provider (the "
                "CPU-only build is present).\n\n"
                "To enable it, install the GPU build with\n"
                "    pixi add --pypi onnxruntime-directml\n"
                "(or re-run Help > Install AI ROI Support) and "
                "restart MicroDrop. Until then the encoder "
                "keeps running on the CPU."
            )

    # ------------------------------------------------------------------ #
    # Interaction mode (pick tool)                                         #
    # ------------------------------------------------------------------ #
    def _rest_mode(self):
        return "edit" if self.analysis_model.edit_mode else "pan"

    @observe("analysis_model:ai_pick_button")
    def _toggle_ai_pick(self, event):
        """Arm the pick tool, or put it away if it is already armed —
        the same idiom RoiAnalysisController._arm uses for the draw
        tools, replicated locally to keep the controllers decoupled."""
        model = self.analysis_model
        model.interaction_mode = (
            self._rest_mode() if model.interaction_mode == "ai_pick" else "ai_pick"
        )

    # ------------------------------------------------------------------ #
    # Launchers                                                            #
    # ------------------------------------------------------------------ #
    @observe("analysis_model:canvas_ai_pick")
    def _on_canvas_ai_pick(self, event):
        if not self._ensure_model_ready():
            # Download was cancelled/failed: disarm the pick tool so the
            # next canvas click doesn't re-open the modal download dialog.
            if self.analysis_model.interaction_mode == "ai_pick":
                self.analysis_model.interaction_mode = self._rest_mode()
            return
        current = self.viewer_model.current_path
        if not current or self.viewer_model.array is None:
            return
        x, y = event.new
        refiner = self._refiner_for_current_model()
        self.analysis_model.progress_text = "Segmenting…"
        perspective = self.session.perspective.effective_matrix()
        self.runner.pick(
            refiner,
            str(current),
            warp_frame(self.viewer_model.array, perspective),
            x,
            y,
            cache_id=embedding_id(current, perspective),
        )

    @observe("analysis_model:ai_detect_button")
    def _on_detect(self, event):
        if not self._ensure_model_ready():
            return
        current = self.viewer_model.current_path
        if not current or self.viewer_model.array is None:
            self.analysis_model.progress_text = "No image loaded"
            return
        self.analysis_model.ai_candidates = []
        refiner = self._refiner_for_current_model()
        self.analysis_model.progress_text = "AI detecting…"
        perspective = self.session.perspective.effective_matrix()
        self.runner.detect_all(
            refiner,
            str(current),
            warp_frame(self.viewer_model.array, perspective),
            capture_timestamp(current),
            cache_id=embedding_id(current, perspective),
        )

    @observe("analysis_model:ai_track_button")
    def _on_track(self, event):
        if self.runner.track_running:
            self.runner.cancel()
            return
        if not self._ensure_model_ready():
            return
        current = self.viewer_model.current_path
        paths = self.viewer_model.paths
        strings = [str(path) for path in paths]
        if current not in strings:
            self.analysis_model.progress_text = "No later frames to track"
            return
        later = [
            path
            for path in paths[strings.index(current) + 1 :]
            if not self.session.is_excluded(path)
        ]
        if not later:
            self.analysis_model.progress_text = "No later frames to track"
            return
        frames = [(str(path), capture_timestamp(path)) for path in later]
        start_geometries = {
            roi_id: centre_of(kind, geometry)
            for roi_id, _name, kind, geometry in self.session.effective_for(current)
        }
        if not start_geometries:
            self.analysis_model.progress_text = "No ROIs to track"
            return
        refiner = self._refiner_for_current_model()
        self.analysis_model.ai_track_done = 0
        self.analysis_model.ai_track_total = 0
        # Say something immediately: the first frame's encode takes
        # seconds, and until it finishes no TRACK_FRAME arrives.
        self.analysis_model.progress_text = (
            f"Drift check starting ({len(frames)} frames)…"
        )
        self.analysis_model.ai_track_running = True
        self.runner.track(
            refiner,
            frames,
            start_geometries,
            self.analysis_model.ai_drift_interval,
            self.session.perspective.effective_matrix(),
        )

    # ------------------------------------------------------------------ #
    # Candidate review                                                     #
    # ------------------------------------------------------------------ #
    @observe("analysis_model:canvas_candidate_clicked")
    def _on_candidate_clicked(self, event):
        index = event.new
        candidates = self.analysis_model.ai_candidates
        if 0 <= index < len(candidates):
            candidates[index].discarded = not candidates[index].discarded

    @observe("analysis_model:ai_accept_button")
    def _on_accept(self, event):
        model = self.analysis_model
        pairs = [
            candidate.geometry_for(model.ai_output_kind)
            for candidate in model.ai_candidates
            if not candidate.discarded
            and candidate.passes(
                model.ai_significance, model.ai_min_size, model.ai_max_size
            )
        ]
        if pairs:
            model.ai_rois_accepted = (pairs, self._detect_anchor)
        model.ai_candidates = []

    @observe("analysis_model:ai_clear_button")
    def _on_clear(self, event):
        self.analysis_model.ai_candidates = []

    @observe(
        "analysis_model:ai_candidates.items, analysis_model:ai_candidates, "
        "analysis_model:ai_significance, analysis_model:ai_min_size, "
        "analysis_model:ai_max_size, "
        "analysis_model:ai_candidates:items:discarded"
    )
    def _update_accept_count(self, event):
        model = self.analysis_model
        model.ai_accept_count = len(
            [
                candidate
                for candidate in model.ai_candidates
                if not candidate.discarded
                and candidate.passes(
                    model.ai_significance, model.ai_min_size, model.ai_max_size
                )
            ]
        )

    # ------------------------------------------------------------------ #
    # Draining the job runner                                              #
    # ------------------------------------------------------------------ #
    def drain_results(self):
        """Called by the dock pane's drain QTimer (GUI thread): move
        finished SAM job results from the runner's queue into the model.
        Each message is handled in isolation so a bad payload logs a
        warning instead of stalling the whole drain."""
        while True:
            try:
                kind, payload = self.runner.results.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle_result(kind, payload)
            except Exception as error:
                logger.warning(f"AI result handling failed ({kind}): {error}")

    def _handle_result(self, kind, payload):
        model = self.analysis_model
        if kind == PICK_RESULT:
            candidate = payload["candidate"]
            if candidate is None:
                model.progress_text = "No droplet found there"
                return
            # Anchor to the launch-time frame (payload["image_id"]), not
            # viewer_model.current_path: the frame can have changed during
            # the encode (slideshow advance or user navigation) by the
            # time this result drains.
            image_id = payload["image_id"]
            anchor = capture_timestamp(image_id) if image_id else 0.0
            model.ai_rois_accepted = (
                [candidate.geometry_for(model.ai_output_kind)],
                anchor,
            )
            model.progress_text = "AI ROI added"
        elif kind == DETECT_PROGRESS:
            model.progress_text = f"AI detect {payload['done']}/{payload['total']}"
        elif kind == DETECT_RESULT:
            self._detect_anchor = payload["capture_time"]
            model.ai_candidates = payload["candidates"]
            model.progress_text = (
                f"{len(payload['candidates'])} candidates — filter, then Accept"
            )
        elif kind == TRACK_FRAME:
            model.ai_track_done = payload["done"]
            model.ai_track_total = payload["total"]
            model.progress_text = (
                f"Drift check {payload['done']}/{payload['total']} frames"
            )
            for roi_id, candidate in payload["candidates"].items():
                if candidate is not None:
                    model.ai_roi_tracked = (
                        roi_id,
                        payload["capture_time"],
                        candidate.geometry_for(model.ai_output_kind)[1],
                    )
        elif kind == TRACK_FINISHED:
            model.ai_track_running = False
            # frames_done counts segmented frames actually processed (every
            # interval-th frame, plus the last); total counts every later
            # frame including the skipped ones the segmenter never touches
            # -- the two aren't the same unit, so "m/n" always read like an
            # early stop when interval > 1. Report only the honest count.
            model.progress_text = (
                f"Drift tracking done ({payload['frames_done']} frames checked)"
            )
        elif kind == AI_FAILED:
            # Already logged (with more detail) by the runner itself.
            model.progress_text = f"AI {payload['stage']} failed: {payload['error']}"
            if model.interaction_mode == "ai_pick":
                # Disarm the pick tool: a failed pick left it armed, so the
                # next canvas click would just relaunch into the same
                # failure instead of doing nothing.
                model.interaction_mode = self._rest_mode()
