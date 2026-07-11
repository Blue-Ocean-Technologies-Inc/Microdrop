"""Playback canvas for the recordings viewer: a QGraphicsView hosting a
QMediaPlayer-fed video item, switchable between the raw camera view and
the device-aligned (perspective-warped) view reconstructed from the
recording's ``.transform.json`` sidecar (written by NativeVideoRecorder).

The canvas is zoomable (wheel, anchored under the cursor) and pannable
(drag); the framing persists to preferences because the alignment
transform can push the frame outside the pane's bounds. It also renders
and edits the model's region-of-interest keyframes (the Edit Region
mode): dragging in edit mode sets the region at the current playback
position.
"""
import json
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QTransform
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView

from logger.logger_service import get_logger

from ...consts import RECORDING_TRANSFORM_SIDECAR_SUFFIX
from ...preferences import DeviceViewerPreferences
from ...utils.camera import qtransform_deserialize

logger = get_logger(__name__)

#: Ignore seek-slider echoes closer than this to the player's position
#: (the player's own positionChanged updates the slider ~25x a second).
SEEK_ECHO_TOLERANCE_MS = 300

#: Wheel zoom step per notch, and the debounce before the current
#: zoom/pan framing is written to preferences.
ZOOM_STEP_FACTOR = 1.2
VIEW_STATE_SAVE_DEBOUNCE_MS = 500

#: Regions smaller than this (scene units) are treated as stray clicks.
MIN_ROI_SIZE = 4.0


class VideoPlaybackCanvas(QGraphicsView):
    """Renders the model's current recording; follows its playback,
    aligned-view, framing and ROI traits and reflects the player's real
    state back."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._sidecar = None
        self._syncing_position = False
        self._restoring_view = False
        self._roi_drag_origin = None
        self._preferences = DeviceViewerPreferences()

        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setBackgroundBrush(Qt.black)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._video_item = QGraphicsVideoItem()
        self.scene().addItem(self._video_item)

        roi_pen = QPen(QColor("#FFD60A"), 0)
        roi_pen.setStyle(Qt.PenStyle.DashLine)
        self._roi_item = QGraphicsRectItem()
        self._roi_item.setPen(roi_pen)
        self._roi_item.setZValue(10)
        self._roi_item.setVisible(False)
        self.scene().addItem(self._roi_item)

        self._player = QMediaPlayer(self)
        self._player.setVideoOutput(self._video_item)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._video_item.nativeSizeChanged.connect(self._on_native_size)

        # Debounced persistence of the zoom/pan framing.
        self._view_state_timer = QTimer(self)
        self._view_state_timer.setSingleShot(True)
        self._view_state_timer.setInterval(VIEW_STATE_SAVE_DEBOUNCE_MS)
        self._view_state_timer.timeout.connect(self._save_view_state)
        self.horizontalScrollBar().valueChanged.connect(self._on_view_panned)
        self.verticalScrollBar().valueChanged.connect(self._on_view_panned)

        model.observe(self._on_current_path_changed, "current_path")
        model.observe(self._on_aligned_changed, "aligned")
        model.observe(self._on_playing_changed, "playing")
        model.observe(self._on_seek_requested, "position_ms")
        model.observe(self._on_active_roi_changed, "active_roi")
        model.observe(self._on_roi_edit_mode_changed, "roi_edit_mode")
        model.observe(self._on_fit_requested, "fit_request")

    # ------------------------------------------------------------------ #
    # Model -> player                                                      #
    # ------------------------------------------------------------------ #
    def _on_current_path_changed(self, event):
        path = event.new
        self._player.stop()
        self._sidecar = self._read_sidecar(path) if path else None
        self._model.has_transform = self._sidecar is not None
        if not self._model.has_transform:
            self._model.aligned = False
        if path:
            self._player.setSource(QUrl.fromLocalFile(path))
            # Show the first frame immediately (source alone stays blank).
            self._player.play()
            self._player.pause()
        self._apply_view()

    def _on_aligned_changed(self, event):
        self._apply_view()

    def _on_playing_changed(self, event):
        if event.new:
            self._player.play()
        else:
            self._player.pause()

    def _on_seek_requested(self, event):
        if self._syncing_position:
            return
        if abs(event.new - self._player.position()) > SEEK_ECHO_TOLERANCE_MS:
            self._player.setPosition(int(event.new))

    # ------------------------------------------------------------------ #
    # Player -> model                                                      #
    # ------------------------------------------------------------------ #
    def _on_duration_changed(self, duration):
        self._model.duration_ms = int(duration)

    def _on_position_changed(self, position):
        self._syncing_position = True
        try:
            self._model.position_ms = min(int(position),
                                          self._model.duration_ms)
        finally:
            self._syncing_position = False

    def _on_playback_state(self, state):
        self._model.playing = (state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_native_size(self, size):
        if not self._model.aligned and not size.isEmpty():
            self._video_item.setSize(size)
            self._apply_view()

    # ------------------------------------------------------------------ #
    # Raw vs device-aligned rendering                                      #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_sidecar(video_path):
        sidecar_path = Path(video_path).with_suffix(
            RECORDING_TRANSFORM_SIDECAR_SUFFIX)
        if not sidecar_path.is_file():
            return None
        try:
            return json.loads(sidecar_path.read_text())
        except Exception as e:
            logger.warning(f"Unreadable transform sidecar {sidecar_path}: {e}")
            return None

    def _apply_view(self):
        """Aligned: reproduce the live scene's geometry — the item sized to
        its recorded bounding rect with the alignment transform applied,
        framed on the recorded scene rect. Raw: identity at native size.
        Framing comes from the persisted zoom/pan when set, else a fit."""
        if self._model.aligned and self._sidecar is not None:
            transform = qtransform_deserialize(
                json.dumps(self._sidecar["transform"]))
            bounding = self._sidecar["bounding_rect"]
            scene_bounding = self._sidecar["scene_bounding_rect"]
            # Reproduce the live item's content rect EXACTLY: the recorded
            # bounding_rect is the video content's rect INSIDE the item —
            # including a non-zero origin (the letterbox offset), which the
            # alignment transform was calibrated against. Content at (0,0)
            # lands the warp over a thousand scene units off. Fill the rect
            # like the live pipeline's drawImage did (no re-letterboxing).
            self._video_item.setAspectRatioMode(
                Qt.AspectRatioMode.IgnoreAspectRatio)
            self._video_item.setOffset(QPointF(bounding[0], bounding[1]))
            self._video_item.setSize(QSizeF(bounding[2], bounding[3]))
            self._video_item.setTransform(transform)
            frame_rect = QRectF(*scene_bounding)
        else:
            self._video_item.setAspectRatioMode(
                Qt.AspectRatioMode.KeepAspectRatio)
            self._video_item.setOffset(QPointF(0, 0))
            self._video_item.setTransform(QTransform())
            native = self._video_item.nativeSize()
            if not native.isEmpty():
                self._video_item.setSize(native)
            frame_rect = self._video_item.sceneBoundingRect()
        if frame_rect.isEmpty():
            return
        # Margin so an out-of-bounds warp can still be panned into view.
        margin = max(frame_rect.width(), frame_rect.height())
        self.scene().setSceneRect(
            frame_rect.adjusted(-margin, -margin, margin, margin))
        self._restore_view_state(frame_rect)

    # ------------------------------------------------------------------ #
    # Zoom / pan, persisted to preferences                                 #
    # ------------------------------------------------------------------ #
    def _restore_view_state(self, frame_rect):
        self._restoring_view = True
        try:
            zoom = self._preferences.video_viewer_zoom
            if zoom > 0:
                self.setTransform(QTransform.fromScale(zoom, zoom))
                self.centerOn(self._preferences.video_viewer_center_x,
                              self._preferences.video_viewer_center_y)
            else:
                self.fitInView(frame_rect, Qt.AspectRatioMode.KeepAspectRatio)
        finally:
            self._restoring_view = False

    def _save_view_state(self):
        center = self.mapToScene(self.viewport().rect().center())
        self._preferences.video_viewer_zoom = float(self.transform().m11())
        self._preferences.video_viewer_center_x = float(center.x())
        self._preferences.video_viewer_center_y = float(center.y())

    def _on_view_panned(self, _value):
        if not self._restoring_view:
            self._view_state_timer.start()

    def wheelEvent(self, event):
        factor = (ZOOM_STEP_FACTOR if event.angleDelta().y() > 0
                  else 1.0 / ZOOM_STEP_FACTOR)
        self.scale(factor, factor)
        self._view_state_timer.start()
        event.accept()

    def _on_fit_requested(self, event):
        """Fit the frame and forget the persisted framing (the escape
        hatch when a warp has been panned/zoomed out of sight)."""
        self._preferences.video_viewer_zoom = 0.0
        self._apply_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only refit automatically while no user framing is persisted.
        if (self._preferences.video_viewer_zoom == 0
                and not self._video_item.sceneBoundingRect().isEmpty()):
            self._restore_view_state(self._video_item.sceneBoundingRect())

    # ------------------------------------------------------------------ #
    # Region of interest: overlay + rubber-band editing                    #
    # ------------------------------------------------------------------ #
    def _on_active_roi_changed(self, event):
        region = self._model.active_roi
        if region:
            self._roi_item.setRect(QRectF(*region))
            self._roi_item.setVisible(True)
        else:
            self._roi_item.setVisible(False)

    def _on_roi_edit_mode_changed(self, event):
        # Rubber-banding needs the drag, panning otherwise.
        self.setDragMode(QGraphicsView.DragMode.NoDrag if event.new
                         else QGraphicsView.DragMode.ScrollHandDrag)

    def mousePressEvent(self, event):
        if self._model.roi_edit_mode and event.button() == Qt.LeftButton:
            self._roi_drag_origin = self.mapToScene(event.position().toPoint())
            self._roi_item.setRect(QRectF(self._roi_drag_origin,
                                          self._roi_drag_origin))
            self._roi_item.setVisible(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._roi_drag_origin is not None:
            current = self.mapToScene(event.position().toPoint())
            self._roi_item.setRect(
                QRectF(self._roi_drag_origin, current).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._roi_drag_origin is not None:
            region = self._roi_item.rect().normalized()
            self._roi_drag_origin = None
            if (region.width() >= MIN_ROI_SIZE
                    and region.height() >= MIN_ROI_SIZE):
                # Keyframe the region at the CURRENT playback position —
                # drawing at different times makes the crop dynamic.
                self._model.set_roi_keyframe(
                    self._model.position_ms,
                    (region.x(), region.y(), region.width(), region.height()))
            else:
                self._on_active_roi_changed(None)   # stray click: restore
            event.accept()
            return
        super().mouseReleaseEvent(event)


def video_canvas_factory(parent, editor):
    """TraitsUI CustomEditor factory: the editor's object is the model."""
    return VideoPlaybackCanvas(editor.object)
