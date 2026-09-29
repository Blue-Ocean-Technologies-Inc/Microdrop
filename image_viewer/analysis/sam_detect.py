# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""SAM droplet detection: osam session, point/grid segmentation, and
candidate conversion. Qt-free (numpy/cv2 in-and-out), importable with or
without the optional ``osam`` package — ``sam_available()`` reports which.

Ported from the standalone droplet_roi prototype (labelme-derived); see
docs/superpowers/specs/2026-08-07-automatic-roi-identification-design.md.
"""

# Standard library imports.
import collections
import threading
from concurrent.futures import ThreadPoolExecutor

# Third-party imports.
import cv2
import numpy as np

# Enthought library imports.
from traits.api import (
    Array,
    Bool,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
)

# Local imports.
from .consts import (
    AI_DETECT_GRID_TARGET_POINTS,
    AI_DETECT_MAX_MASK_AREA_FRACTION,
    AI_DETECT_MIN_MASK_AREA_PX,
    AI_ENCODE_WORK_WIDTH_PX,
    AI_NORMALIZE_HIGH_PERCENTILE,
    AI_NORMALIZE_LOW_PERCENTILE,
)
from .roi_geometry import normalize

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

try:
    import osam
except ImportError:  # optional dependency: Help menu installs it
    osam = None

#: Set once _patch_osam_providers() has actually run, so a later
#: sam_available() retry (after an in-process Help-menu install) and the
#: module-bottom call below can't both patch the providers twice.
_providers_patched = False

#: (model_name, display_name) — PROTO sam.py MODEL_OPTIONS, labelme's
#: point-prompt AI-assist list, speed -> accuracy within each family.
AI_MODEL_OPTIONS = (
    ("efficientsam:10m", "EfficientSam (speed)"),
    ("efficientsam:latest", "EfficientSam (accuracy)"),
    ("sam:100m", "Sam (speed)"),
    ("sam:300m", "Sam (balanced)"),
    ("sam:latest", "Sam (accuracy)"),
    ("sam2:small", "Sam2 (speed)"),
    ("sam2:latest", "Sam2 (balanced)"),
    ("sam2:large", "Sam2 (accuracy)"),
)
DEFAULT_AI_MODEL = "efficientsam:latest"

#: Preference-driven: whether encoders built from now on may use the
#: DirectML GPU provider (checked at session-load time by the provider
#: patch, so a toggle + refiner rebuild applies without a restart).
_gpu_encoder_enabled = True


def set_gpu_encoder_enabled(enabled):
    """Preference hook for the GPU toggle; rebuild the refiner after
    calling for it to take effect on the next encoder session."""
    global _gpu_encoder_enabled
    _gpu_encoder_enabled = bool(enabled)


def gpu_encoder_available():
    """Whether onnxruntime carries the DirectML provider (the GPU build,
    onnxruntime-directml). False also when osam is absent."""
    if not sam_available():
        return False
    # optional dependency: only reachable once osam (which depends on
    # onnxruntime) is installed
    import onnxruntime

    return "DmlExecutionProvider" in onnxruntime.get_available_providers()


def sam_available():
    """Whether the optional osam stack imported -- retrying the import if
    it was not present at module load time (e.g. the Help-menu installer
    has since run `pixi add --pypi osam` in-process), so a successful
    install becomes usable without an app restart."""
    global osam
    if osam is None:
        try:
            # optional dependency: Help menu installs it
            import osam as _osam
        except ImportError:
            return False
        osam = _osam
    _patch_osam_providers_once()
    return osam is not None


def normalize_to_uint8(
    array, low_pct=AI_NORMALIZE_LOW_PERCENTILE, high_pct=AI_NORMALIZE_HIGH_PERCENTILE
):
    """Percentile-clip contrast stretch to uint8 (PROTO imaging.py)."""
    if array.dtype == np.uint8 and array.max() > 200:
        return array
    array = array.astype(np.float64)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)
    low, high = np.percentile(finite, [low_pct, high_pct])
    if high - low <= 0:
        return np.zeros(array.shape, dtype=np.uint8)
    normalized = (array - low) / (high - low) * 255
    return np.nan_to_num(np.clip(normalized, 0, 255), nan=0.0).astype(np.uint8)


def to_rgb(gray_u8):
    """Stack grayscale to (H, W, 3) as the SAM encoder requires."""
    return np.stack([gray_u8] * 3, axis=-1)


class Detection(HasTraits):
    """One SAM mask, in the OSAM annotation contract used across
    labelme's _automation package: bbox is (xmin, ymin, xmax, ymax) in
    full-image coordinates, mask is a bool array covering exactly the
    inclusive bbox extent (ymax - ymin + 1, xmax - xmin + 1)."""

    #: xmin, ymin, xmax, ymax
    bbox = List(Float)
    #: local, bbox-sized
    mask = Array(dtype=bool)
    score = Float()


class Candidate(HasTraits):
    """A detection converted to plugin geometry: a fitted ellipse and a
    polygon outline, plus the vote-count/click provenance that decides
    whether it survives significance filtering."""

    #: flat x1, y1, x2, y2, ... in full-image coords
    polygon = List(Float)
    #: cx, cy, rx, ry, angle_deg
    ellipse = List(Float)
    #: how many grid points independently produced this mask in a
    #: Detect-all sweep. Click-added candidates keep 1 but are exempt
    #: from filtering.
    votes = Int(1)
    score = Float(0.0)
    #: the click that produced this candidate, in full-image coords.
    #: Re-detect replays this prompt on the current frame to track
    #: droplet drift.
    prompt = List(Float)
    discarded = Bool(False)
    #: "auto" (grid sweep) | "click" (user-asserted)
    source = Str("auto")

    #: Mean ellipse diameter in px -- the "size" the filter slider uses.
    size = Property(Float, observe="ellipse.items")

    def _get_size(self):
        if len(self.ellipse) < 5:
            return 0.0
        return self.ellipse[2] + self.ellipse[3]

    def geometry_for(self, kind):
        """(kind, geometry) in canonical plugin form, via
        ``roi_geometry.normalize``."""
        if kind == "polygon":
            return normalize("polygon", list(self.polygon))
        return normalize("ellipse", list(self.ellipse))

    def passes(self, min_votes, min_size, max_size):
        """Whether this candidate survives significance filtering.
        Click-sourced candidates are exempt from the vote threshold;
        the size window applies to all."""
        return (
            self.source == "click" or self.votes >= min_votes
        ) and min_size <= self.size <= max_size


def candidate_from_detection(detection, prompt=None, votes=1, source="auto"):
    """Convert a SAM mask to a fitted ellipse + polygon outline
    ``Candidate``."""
    mask = detection.mask
    if mask is None or not mask.any():
        return None

    xmin, ymin = detection.bbox[0], detection.bbox[1]
    # 1-px pad so masks touching the bbox border still close their contour.
    padded = np.pad(mask.astype(np.uint8), 1)
    contours, _ = cv2.findContours(padded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=lambda c: cv2.arcLength(c, closed=True))
    contour = contour.reshape(-1, 2).astype(np.float64) - 1.0  # undo pad

    if len(contour) >= 5:
        (ecx, ecy), (ew, eh), angle = cv2.fitEllipse(contour.astype(np.float32))
        rx, ry = ew / 2.0, eh / 2.0
    else:
        ecx, ecy = contour.mean(axis=0)
        rx = ry = float(np.sqrt(np.count_nonzero(mask) / np.pi))
        angle = 0.0

    epsilon = 0.004 * max(np.ptp(contour, axis=0)) if len(contour) > 2 else 1.0
    approx = cv2.approxPolyDP(
        contour.astype(np.float32), epsilon=float(epsilon), closed=True
    ).reshape(-1, 2)

    polygon = (approx + [xmin, ymin]).tolist()
    return Candidate(
        polygon=[coordinate for point in polygon for coordinate in point],
        ellipse=[
            float(ecx + xmin),
            float(ecy + ymin),
            float(rx),
            float(ry),
            float(angle),
        ],
        score=detection.score,
        prompt=list(prompt) if prompt is not None else [],
        votes=votes,
        source=source,
    )


def suppress_with_votes(pairs, iou_threshold=0.5):
    """Greedy dedup by score (IoU >= threshold, or intersection-over-smaller
    >= 0.85 for nested masks -- mirrors labelme's suppress_detections_greedy).
    Input carries per-detection initial votes (grid points that supported it);
    votes of merged duplicates are summed into the kept detection -- that
    total is the candidate's significance."""
    kept = []  # [Detection, votes]
    for detection, votes in sorted(pairs, key=lambda pair: -pair[0].score):
        for entry in kept:
            if _is_redundant(detection, entry[0], iou_threshold):
                entry[1] += votes
                break
        else:
            kept.append([detection, votes])
    return [(detection, votes) for detection, votes in kept]


def _is_redundant(a, b, iou_threshold):
    intersection = _mask_intersection_area(a, b)
    if intersection == 0:
        return False
    area_a = int(np.count_nonzero(a.mask))
    area_b = int(np.count_nonzero(b.mask))
    iou = intersection / (area_a + area_b - intersection)
    containment = intersection / max(min(area_a, area_b), 1)
    return iou >= iou_threshold or containment >= 0.85


def _mask_intersection_area(a, b):
    ax0, ay0 = (int(round(v)) for v in a.bbox[:2])
    bx0, by0 = (int(round(v)) for v in b.bbox[:2])
    x0 = max(ax0, bx0)
    y0 = max(ay0, by0)
    x1 = min(ax0 + a.mask.shape[1], bx0 + b.mask.shape[1])
    y1 = min(ay0 + a.mask.shape[0], by0 + b.mask.shape[0])
    if x0 >= x1 or y0 >= y1:
        return 0
    sub_a = a.mask[y0 - ay0 : y1 - ay0, x0 - ax0 : x1 - ax0]
    sub_b = b.mask[y0 - by0 : y1 - by0, x0 - bx0 : x1 - bx0]
    return int(np.count_nonzero(sub_a & sub_b))


def _patch_osam_providers():
    """Route SAM encoders through DirectML when available (osam only
    auto-detects CUDA). Measured on this machine's Radeon 780M: encode 3.2x
    faster on DML; the small decoder is FASTER on CPU (GPU transfer overhead
    dominates), so decoders keep the CPU provider."""
    # optional dependency: this module only runs when osam is installed
    import onnxruntime

    if "DmlExecutionProvider" not in onnxruntime.get_available_providers():
        return
    from osam.types import _model as osam_model

    original = osam_model._load_inference_session

    def load_with_best_provider(blob, providers=None):
        # _gpu_encoder_enabled is read at load time, so flipping the
        # preference and rebuilding the refiner switches providers
        # without a restart.
        use_dml = (
            _gpu_encoder_enabled and "encoder" in getattr(blob, "filename", "").lower()
        )
        try:
            return onnxruntime.InferenceSession(
                blob.path,
                providers=(
                    ["DmlExecutionProvider", "CPUExecutionProvider"]
                    if use_dml
                    else ["CPUExecutionProvider"]
                ),
            )
        except Exception:
            return original(blob=blob, providers=providers)

    osam_model._load_inference_session = load_with_best_provider


def _patch_osam_providers_once():
    """Run _patch_osam_providers() at most once, however many times
    sam_available() or the module-bottom call below try to trigger it."""
    global _providers_patched
    if _providers_patched or osam is None:
        return
    _patch_osam_providers()
    _providers_patched = True


class OsamSession(HasTraits):
    """Thread-safe: the tracking pipeline encodes the next frame on a
    prefetch thread while decode calls run on others (onnxruntime sessions
    support concurrent run())."""

    #: which osam model this session wraps.
    _model_name = Str()
    #: how many image embeddings to keep before evicting the oldest.
    cache_size = Int(8)
    _model = Instance(object)
    _embedding_cache = Instance(collections.deque)
    _lock = Instance(object)

    def __embedding_cache_default(self):
        return collections.deque(maxlen=self.cache_size)

    def __lock_default(self):
        return threading.Lock()

    def ensure_model(self):
        with self._lock:
            if self._model is None:
                self._model = osam.apis.get_model_type_by_name(self._model_name)()
                # osam's own "Initialized inference sessions" line only
                # shows the LAST session's providers (the decoder, kept
                # on CPU on purpose) — log the true per-session split.
                providers = {
                    key: session.get_providers()[0]
                    for key, session in self._model._inference_sessions.items()
                }
                logger.info(f"SAM {self._model_name} session providers: {providers}")
            return self._model

    def ensure_embedding(self, image, image_id):
        with self._lock:
            for key, embedding in self._embedding_cache:
                if key == image_id:
                    return embedding
        embedding = self.ensure_model().encode_image(image=image)
        with self._lock:
            self._embedding_cache.append((image_id, embedding))
        return embedding

    def run(self, image, image_id, points, point_labels):
        embedding = self.ensure_embedding(image=image, image_id=image_id)
        model = self.ensure_model()
        return model.generate(
            request=osam.types.GenerateRequest(
                model=model.name,
                image=image,
                image_embedding=embedding,
                prompt=osam.types.Prompt(points=points, point_labels=point_labels),
            )
        )


class SamRefiner(HasTraits):
    """Point-prompt segmentation on a downscaled image, results at full
    res."""

    model_name = Str(DEFAULT_AI_MODEL)
    work_width = Int(AI_ENCODE_WORK_WIDTH_PX)
    #: how many prepared (downscaled-image, scale) entries to keep before
    #: evicting the oldest.
    work_cache_size = Int(8)
    _session = Instance(OsamSession)
    _lock = Instance(object)
    #: image_id -> (work_rgb, scale); keyed cache instead of mutable
    #: current-frame state so prepare/segment can run on different threads.
    _work_cache = Instance(collections.OrderedDict)

    def __session_default(self):
        return OsamSession(_model_name=self.model_name)

    def __lock_default(self):
        return threading.Lock()

    def __work_cache_default(self):
        return collections.OrderedDict()

    def traits_init(self):
        if not sam_available():
            raise RuntimeError("osam is not installed")

    def prepare(self, image_id, gray_u8):
        """Downscale + encode (slow, seconds); later prompts are
        sub-second."""
        with self._lock:
            cached = self._work_cache.get(image_id)
        if cached is None:
            h, w = gray_u8.shape
            if w > self.work_width:
                scale = w / self.work_width
                work = cv2.resize(
                    gray_u8,
                    (self.work_width, int(round(h / scale))),
                    interpolation=cv2.INTER_AREA,
                )
            else:
                scale = 1.0
                work = gray_u8
            cached = (to_rgb(work), scale)
            with self._lock:
                self._work_cache[image_id] = cached
                while len(self._work_cache) > self.work_cache_size:
                    self._work_cache.popitem(last=False)
        self._session.ensure_embedding(cached[0], image_id)

    def segment_point(self, image_id, x_full, y_full):
        with self._lock:
            cached = self._work_cache.get(image_id)
        assert cached is not None, "call prepare() first"
        work_rgb, scale = cached
        response = self._session.run(
            image=work_rgb,
            image_id=image_id,
            points=np.array([[x_full / scale, y_full / scale]]),
            point_labels=np.array([1], dtype=np.intp),
        )
        best = None
        for annotation in response.annotations:
            if annotation.mask is None or annotation.bounding_box is None:
                continue
            if best is None or (annotation.score or 0) > (best.score or 0):
                best = annotation
        if best is None:
            return None
        return self._upscale(best, scale)

    def segment_grid(
        self,
        image_id,
        image_shape,
        target_points=AI_DETECT_GRID_TARGET_POINTS,
        progress_cb=None,
    ):
        """Detect-everything sweep: prompt the decoder on a point grid
        spanning the whole frame against the one cached embedding. Every
        point is decoded -- an earlier covered-point skip was measured to
        silently drop droplets overlapped by a neighbor's mask -- but the
        decodes are independent, so they run in a thread pool (~2x).
        Returns (detection, prompt_point, votes) triples with votes=1 each;
        duplicate-mask merging in suppress_with_votes sums them into the
        significance count. Degenerate masks (background grabs, specks) are
        dropped. Call prepare() first."""
        h, w = image_shape
        nx = max(2, int(round(np.sqrt(target_points * w / max(h, 1)))))
        ny = max(2, int(round(target_points / nx)))
        points = [
            (float((ix + 0.5) / nx * w), float((iy + 0.5) / ny * h))
            for iy in range(ny)
            for ix in range(nx)
        ]

        done = 0
        done_lock = threading.Lock()

        def decode(point):
            nonlocal done
            detection = self.segment_point(image_id, point[0], point[1])
            with done_lock:
                done += 1
                if progress_cb is not None:
                    progress_cb(done, len(points))
            return detection

        with ThreadPoolExecutor(max_workers=4) as pool:
            detections = list(pool.map(decode, points))

        frame_area = w * h
        results = []
        for point, detection in zip(points, detections):
            if detection is None:
                continue
            area = int(np.count_nonzero(detection.mask))
            # Reject background grabs and specks. Generous bounds: real
            # droplets are far inside them, whole-image masks far outside.
            if not (
                AI_DETECT_MIN_MASK_AREA_PX
                <= area
                <= AI_DETECT_MAX_MASK_AREA_FRACTION * frame_area
            ):
                continue
            results.append((detection, [point[0], point[1]], 1))
        return results

    @staticmethod
    def _upscale(annotation, s):
        bb = annotation.bounding_box
        xmin = int(round(bb.xmin * s))
        ymin = int(round(bb.ymin * s))
        xmax = int(round((bb.xmax + 1) * s)) - 1
        ymax = int(round((bb.ymax + 1) * s)) - 1
        w = xmax - xmin + 1
        h = ymax - ymin + 1
        if w <= 0 or h <= 0:
            return None
        mask = cv2.resize(
            annotation.mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST
        ).astype(bool)
        return Detection(
            bbox=[float(xmin), float(ymin), float(xmax), float(ymax)],
            mask=mask,
            score=float(annotation.score or 0.0),
        )


if osam is not None:
    _patch_osam_providers_once()
