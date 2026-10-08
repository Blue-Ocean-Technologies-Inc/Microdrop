# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI view for the image viewer pane: the toolbar bound to the model
and the image canvas editor (zoom/pan QGraphicsView rendering the model's
``array`` through the display window, reporting the hovered pixel back).
"""

# Third-party imports.
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QProgressBar,
    QSizePolicy,
)

# Enthought library imports.
from traits.api import Enum, Float, HasTraits
from traitsui.api import (
    BasicEditorFactory,
    Group,
    HGroup,
    HSplit,
    Item,
    Label,
    RangeEditor,
    UItem,
    VGroup,
    View,
    spring,
)
from traitsui.qt.editor import Editor as QtEditor

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_ADJUST,
    ICON_CANCEL,
    ICON_CAPSULE,
    ICON_CHEVRON_LEFT,
    ICON_CHEVRON_RIGHT,
    ICON_CIRCLE,
    ICON_CONTOUR,
    ICON_COPY,
    ICON_CROP,
    ICON_DELETE,
    ICON_DELETE_SWEEP,
    ICON_EDIT,
    ICON_FOLDER_OPEN,
    ICON_HOME,
    ICON_NEXT,
    ICON_OPEN_IN_NEW,
    ICON_PASTE,
    ICON_PAUSE,
    ICON_PLAY,
    ICON_PREVIOUS,
    ICON_RECTANGLE,
    ICON_REFRESH,
    ICON_RESET_WRENCH,
    ICON_RULER,
    ICON_SAVE,
    ICON_SHOW_CHART,
    ICON_TONALITY,
    ICON_TRANSFORM,
    ICON_VIEW_3D,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    DoubleSpinBoxEditor,
    HoverScrollEnumEditor,
    IconButtonEditor,
    IconModeButtonEditor,
    IconToggleEditor,
)

# Local imports.
from .analysis.consts import (
    AI_SIZE_FILTER_CEILING_PX,
    RING_GAP_BOUNDS_PX,
    RING_THICKNESS_BOUNDS_PX,
    ROLLING_BALL_RADIUS_BOUNDS_PX,
)
from .analysis.roi_canvas_layer import RoiCanvasLayer
from .consts import IMAGE_ZOOM_STEP_BOUNDS, IMAGE_ZOOM_STEP_DEFAULT
from .display import frame_to_qimage
from .scale_bar import (
    DEFAULT_UNIT,
    UNITS,
    metres_per_pixel,
    nice_scale,
)
from .scale_layer import ScaleCanvasLayer

#: Inset of the scale bar from the viewport's bottom-left corner.
SCALE_BAR_MARGIN_PX = 12

#: The scale bar's backdrop and lettering, in viewport pixels:
#: padding around the bar, the backdrop height, the end ticks, and
#: the text row above the bar.
SCALE_BAR_PAD_PX = 6
SCALE_BAR_BOX_HEIGHT_PX = 32
SCALE_BAR_TICK_PX = 5
SCALE_BAR_TEXT_RISE_PX = 24
SCALE_BAR_TEXT_HEIGHT_PX = 18

#: Shortest interval between hovered-pixel readout repaints (~30 Hz):
#: mouse moves arrive faster than anyone can read the numbers.
PIXEL_READOUT_INTERVAL_MS = 33

#: Keeps the status row's progress bar from bulking up the row.
PROGRESS_BAR_HEIGHT_PX = 16


class _ProgressReadoutEditor(QtEditor):
    """The batch readout as a progress bar whose text is the model's
    progress_text. It repaints itself on every change: results arrive
    faster than the event loop would otherwise paint, and the point of
    the readout is to be watched while that happens."""

    def init(self, parent):
        self.control = QProgressBar()
        self.control.setTextVisible(True)
        self.control.setMaximumHeight(PROGRESS_BAR_HEIGHT_PX)
        self.update_editor()

    def update_editor(self):
        # TraitsUI resolves a dotted item name down to the object that
        # owns the trait, so this is the RoiAnalysisModel itself.
        analysis = self.object
        if analysis.ai_track_running:
            # A drift check owns the readout while it runs; the batch
            # counts are stale then (often full from the last batch),
            # which read as a stuck bar.
            total, done = analysis.ai_track_total, analysis.ai_track_done
        else:
            total, done = analysis.batch_total, analysis.batch_done
        self.control.setVisible(bool(self.value))
        # An unknown total (a message rather than a count) shows an
        # empty trough behind the text instead of a bogus fraction.
        self.control.setRange(0, total if total else 1)
        self.control.setValue(done if total else 0)
        self.control.setFormat(self.value)
        self.control.repaint()


class ProgressReadoutEditor(BasicEditorFactory):
    """Factory for the batch progress readout over a Str trait."""

    klass = _ProgressReadoutEditor


class ScaleEntry(HasTraits):
    """Modal form asking what the drawn line measures. The dialogs
    wrapper covers message dialogs only, so a two-field form is a
    plain TraitsUI livemodal view."""

    value = Float(1.0)
    unit = Enum(DEFAULT_UNIT, UNITS)

    traits_view = View(
        Item("value", label="Length"),
        Item("unit", label="Units"),
        title="Set image scale",
        buttons=["OK", "Cancel"],
        kind="livemodal",
        width=260,
    )


class _ImageView(QGraphicsView):
    """Zoom (wheel, anchored under the cursor) + pan (drag) image view that
    reports the hovered pixel to a callback. Shrinks/grows freely with the
    dock pane (a full-resolution scene would otherwise dictate a huge size
    hint) and keeps the image fitted on resize until the user zooms."""

    def __init__(self, scene, on_hover, roi_layer, scale_layer):
        super().__init__(scene)
        self._on_hover = on_hover
        self._roi_layer = roi_layer
        self._scale_layer = scale_layer
        #: Set by the editor: fires the copy/paste/delete toolbar
        #: buttons, so the shortcuts and the buttons are one code path.
        self.on_roi_shortcut = lambda action: None
        self._metres_per_pixel = 0.0
        self._pixel_text = ""
        #: The newest readout, shown when the coalescing timer fires.
        self._pending_pixel_text = ""
        self._pixel_text_timer = QTimer(self)
        self._pixel_text_timer.setSingleShot(True)
        self._pixel_text_timer.setInterval(PIXEL_READOUT_INTERVAL_MS)
        self._pixel_text_timer.timeout.connect(self._show_pending_pixel_text)
        self._zoom_step = IMAGE_ZOOM_STEP_DEFAULT
        self._auto_fit = True
        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(self.DragMode.ScrollHandDrag)
        self.setMouseTracking(True)
        # Keys only reach a focused widget, and contour drawing needs
        # Enter/Escape/Backspace once the canvas is clicked.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_zoom_step(self, step):
        """One wheel notch's zoom factor (going out is its
        reciprocal) — the Advanced group's zoom-sensitivity setting."""
        self._zoom_step = step

    def wheelEvent(self, event):
        self._auto_fit = False
        factor = (
            self._zoom_step if event.angleDelta().y() > 0 else 1.0 / self._zoom_step
        )
        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        # A candidate under the cursor wins in every mode, ahead of the
        # scale layer's own draw_scale handling as well as the ROI
        # layer's — the scale ruler has no candidate awareness of its
        # own, so this has to be checked before it gets a turn.
        if self._roi_layer.candidate_click(point):
            event.accept()
            return
        if self._scale_layer.mouse_press(point):
            event.accept()
            return
        if self._roi_layer.mouse_press(point):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        self._on_hover(int(point.x()), int(point.y()))
        if self._scale_layer.mouse_move(point):
            event.accept()
            return
        if self._roi_layer.mouse_move(point):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        if self._scale_layer.mouse_release(point):
            event.accept()
            return
        if self._roi_layer.mouse_release(point):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        if self._roi_layer.mouse_double_click(point):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        # Contour drawing finishes on Enter and unwinds on Escape /
        # Backspace, and Escape also puts an armed draw tool away;
        # everything else falls through to the view.
        if self._roi_layer.key_press(event.key()):
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            action = {Qt.Key.Key_C: "copy", Qt.Key.Key_V: "paste"}.get(event.key())
        else:
            # Delete only, not Backspace: that one takes back a contour
            # vertex while tracing.
            action = "delete" if event.key() == Qt.Key.Key_Delete else None
        if action is not None:
            self.on_roi_shortcut(action)
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit()

    def set_scale(self, metres_per_pixel_value):
        self._metres_per_pixel = metres_per_pixel_value
        self.viewport().update()

    def set_pixel_text(self, text):
        """The hovered pixel's "(x, y) = value" readout, drawn as a HUD
        in the bottom-right corner ('' hides it). Coalesced: the newest
        text shows at most every PIXEL_READOUT_INTERVAL_MS."""
        self._pending_pixel_text = text

        if not self._pixel_text_timer.isActive():
            self._pixel_text_timer.start()

    def _show_pending_pixel_text(self):
        """Repaint just the readout's corner — the old box and the new
        one — rather than the whole viewport and the image under it."""
        if self._pending_pixel_text == self._pixel_text:
            return

        viewport = self.viewport().rect()
        stale = self._pixel_readout_box(self._pixel_text, viewport)
        self._pixel_text = self._pending_pixel_text
        fresh = self._pixel_readout_box(self._pixel_text, viewport)

        self.viewport().update(
            stale.united(fresh).toAlignedRect().adjusted(-2, -2, 2, 2)
        )

    def drawForeground(self, painter, rect):
        """Paint the HUD overlays in viewport pixels: the scale bar in
        the bottom-left corner, the hovered-pixel readout bottom-right."""
        super().drawForeground(painter, rect)
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        viewport = self.viewport().rect()
        self._draw_scale_bar(painter, viewport)
        self._draw_pixel_readout(painter, viewport)
        painter.restore()

    def _draw_scale_bar(self, painter, viewport):
        """Ask nice_scale what a bar of about SCALE_BAR_TARGET_PX
        should read at the current zoom, and draw it."""
        if self._metres_per_pixel <= 0:
            return
        zoom = self.transform().m11()
        if zoom <= 0:
            return
        scale = nice_scale(self._metres_per_pixel / zoom)
        if scale is None:
            return
        bar_px, label = scale
        left = viewport.left() + SCALE_BAR_MARGIN_PX
        bottom = viewport.bottom() - SCALE_BAR_MARGIN_PX
        painter.fillRect(
            QRectF(
                left - SCALE_BAR_PAD_PX,
                bottom - SCALE_BAR_BOX_HEIGHT_PX + SCALE_BAR_PAD_PX,
                bar_px + 2 * SCALE_BAR_PAD_PX,
                SCALE_BAR_BOX_HEIGHT_PX,
            ),
            QColor(0, 0, 0, 110),
        )
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(left, bottom, int(left + bar_px), bottom)
        painter.drawLine(left, bottom - SCALE_BAR_TICK_PX, left, bottom)
        painter.drawLine(
            int(left + bar_px), bottom - SCALE_BAR_TICK_PX, int(left + bar_px), bottom
        )
        painter.drawText(
            QRectF(
                left, bottom - SCALE_BAR_TEXT_RISE_PX, bar_px, SCALE_BAR_TEXT_HEIGHT_PX
            ),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

    def _draw_pixel_readout(self, painter, viewport):
        """The hovered pixel's readout, bottom-right in the scale bar's
        backdrop-and-lettering style (the corner the bar doesn't use)."""
        if not self._pixel_text:
            return

        box = self._pixel_readout_box(self._pixel_text, viewport)
        painter.fillRect(box, QColor(0, 0, 0, 110))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self._pixel_text)

    def _pixel_readout_box(self, text, viewport):
        """The readout's backdrop for ``text`` in viewport pixels — what
        _draw_pixel_readout paints and what a change must repaint; null
        for ''."""
        if not text:
            return QRectF()

        text_px = self.viewport().fontMetrics().horizontalAdvance(text)
        right = viewport.right() - SCALE_BAR_MARGIN_PX
        bottom = viewport.bottom() - SCALE_BAR_MARGIN_PX

        return QRectF(
            right - text_px - 2 * SCALE_BAR_PAD_PX,
            bottom - SCALE_BAR_TEXT_HEIGHT_PX - SCALE_BAR_PAD_PX,
            text_px + 2 * SCALE_BAR_PAD_PX,
            SCALE_BAR_TEXT_HEIGHT_PX + SCALE_BAR_PAD_PX,
        )

    def fit(self):
        if self.scene() is not None and not self.scene().sceneRect().isEmpty():
            self._auto_fit = True
            self.resetTransform()
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def fit_new_image(self, size_changed):
        """Refit for a newly shown image, unless the user has zoomed and
        the image is the same size: stepping through a burst keeps their
        zoom and pan."""
        if size_changed or self._auto_fit:
            self.fit()

    def zoom(self, direction):
        """One zoom step in (+1) or out (-1) — the toolbar buttons'
        path. Anchored on the viewport centre: unlike the wheel there
        is no cursor position to anchor under."""
        self._auto_fit = False
        wheel_anchor = self.transformationAnchor()
        self.setTransformationAnchor(self.ViewportAnchor.AnchorViewCenter)
        factor = self._zoom_step if direction > 0 else 1.0 / self._zoom_step
        self.scale(factor, factor)
        self.setTransformationAnchor(wheel_anchor)


class _ImageCanvasEditor(QtEditor):
    """Canvas bound to the model's ``array``: draws the model's
    ``display_frame`` (rendered off the GUI thread by the controller),
    refits on a newly loaded image unless the user zoomed (and on
    ``fit_request``), redraws in place on window edits, and writes the
    hovered pixel's true value back to ``pixel_text``."""

    scrollable = True

    def init(self, parent):
        self._image_size = None
        self._scene = QGraphicsScene()
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self._roi_layer = RoiCanvasLayer(self._scene)
        analysis = self.object.roi_analysis
        self._roi_layer.on_roi_created = lambda kind, geometry: analysis.trait_set(
            canvas_roi_created=(kind, geometry)
        )
        self._roi_layer.on_roi_edited = lambda roi_id, geometry: analysis.trait_set(
            canvas_roi_edited=(roi_id, geometry)
        )
        self._roi_layer.on_roi_selected = lambda roi_id: analysis.trait_set(
            selected_roi_id=roi_id
        )
        self._roi_layer.on_draw_cancelled = lambda: analysis.trait_set(
            canvas_draw_cancelled=True
        )
        self._roi_layer.on_ball_radius_changed = self._on_ball_radius_dragged
        self._roi_layer.on_ai_pick = lambda x, y: analysis.trait_set(
            canvas_ai_pick=(x, y)
        )
        self._roi_layer.on_candidate_clicked = lambda index: analysis.trait_set(
            canvas_candidate_clicked=index
        )
        self._scale_layer = ScaleCanvasLayer(self._scene)
        self._scale_layer.on_line_drawn = self._on_scale_line_drawn
        self.control = _ImageView(
            self._scene, self._on_hover, self._roi_layer, self._scale_layer
        )
        self.control.on_roi_shortcut = lambda action: analysis.trait_set(
            **{f"{action}_roi_button": True}
        )
        self.control.set_zoom_step(self.object.zoom_step)
        self.object.observe(self._on_zoom_step_changed, "zoom_step")
        self.object.observe(self._on_display_frame_changed, "display_frame")
        self.object.observe(self._on_fit_request, "fit_request")
        self.object.observe(self._on_zoom_request, "zoom_request")
        self.object.observe(
            self._on_roi_state_changed,
            "current_path, roi_analysis:session, "
            "roi_analysis:session:rois.items, "
            "roi_analysis:session:rois:items:geometry, "
            "roi_analysis:session:rois:items:overrides.items, "
            "roi_analysis:session:rois:items:name, "
            "roi_analysis:session:scale:metres_per_pixel, "
            "roi_analysis:session:ring:gap_px, "
            "roi_analysis:session:ring:thickness_px, "
            "roi_analysis:session:ring:show_on_canvas, "
            "roi_analysis:session:ball:enabled, "
            "roi_analysis:session:ball:radius_px, "
            "roi_analysis:session:ball:show_reference, "
            "roi_analysis:selected_roi_id",
        )
        self.object.observe(
            self._on_interaction_mode_changed, "roi_analysis:interaction_mode"
        )
        self.object.observe(
            self._on_ai_candidates_changed,
            "roi_analysis:ai_candidates, "
            "roi_analysis:ai_candidates.items, "
            "roi_analysis:ai_candidates:items:discarded, "
            "roi_analysis:ai_output_kind, "
            "roi_analysis:ai_significance, "
            "roi_analysis:ai_min_size, "
            "roi_analysis:ai_max_size",
        )

        # A rebuilt pane opens on a frame the controller already rendered.
        self._redraw()

    def dispose(self):
        self.object.observe(self._on_zoom_step_changed, "zoom_step", remove=True)
        self.object.observe(
            self._on_display_frame_changed, "display_frame", remove=True
        )
        self.object.observe(self._on_fit_request, "fit_request", remove=True)
        self.object.observe(self._on_zoom_request, "zoom_request", remove=True)
        self.object.observe(
            self._on_roi_state_changed,
            "current_path, roi_analysis:session, "
            "roi_analysis:session:rois.items, "
            "roi_analysis:session:rois:items:geometry, "
            "roi_analysis:session:rois:items:overrides.items, "
            "roi_analysis:session:rois:items:name, "
            "roi_analysis:session:scale:metres_per_pixel, "
            "roi_analysis:session:ring:gap_px, "
            "roi_analysis:session:ring:thickness_px, "
            "roi_analysis:session:ring:show_on_canvas, "
            "roi_analysis:session:ball:enabled, "
            "roi_analysis:session:ball:radius_px, "
            "roi_analysis:session:ball:show_reference, "
            "roi_analysis:selected_roi_id",
            remove=True,
        )
        self.object.observe(
            self._on_interaction_mode_changed,
            "roi_analysis:interaction_mode",
            remove=True,
        )
        self.object.observe(
            self._on_ai_candidates_changed,
            "roi_analysis:ai_candidates, "
            "roi_analysis:ai_candidates.items, "
            "roi_analysis:ai_candidates:items:discarded, "
            "roi_analysis:ai_output_kind, "
            "roi_analysis:ai_significance, "
            "roi_analysis:ai_min_size, "
            "roi_analysis:ai_max_size",
            remove=True,
        )
        super().dispose()

    def update_editor(self):
        # A new image arrived in `array`; its display frame is already
        # drawn (the controller sets it first). A draw or edit during a
        # run keeps the zoom.
        array = self.value
        image_size = None if array is None else array.shape[:2]

        if not self.object.roi_analysis.holds_view:
            self.control.fit_new_image(image_size != self._image_size)

        self._image_size = image_size
        self._sync_roi_layer()

    def _on_zoom_step_changed(self, event):
        self.control.set_zoom_step(event.new)

    def _on_display_frame_changed(self, event):
        self._redraw()  # a window or correction edit keeps the user's zoom

    def _on_fit_request(self, event):
        self.control.fit()

    def _on_zoom_request(self, event):
        self.control.zoom(event.new)

    def _on_roi_state_changed(self, event):
        self._sync_roi_layer()

    def _sync_roi_layer(self):
        model = self.object
        if not model.current_path or model.array is None:
            self._roi_layer.clear_items()
            return
        ring = model.roi_analysis.session.ring
        self._roi_layer.set_ring(ring.gap_px, ring.thickness_px, ring.show_on_canvas)
        ball = model.roi_analysis.session.ball
        self._roi_layer.set_ball_reference(
            ball.enabled and ball.show_reference, ball.radius_px
        )
        self._roi_layer.sync(
            model.roi_analysis.session.effective_for(model.current_path),
            model.roi_analysis.selected_roi_id,
        )
        self._push_scale()

    def _on_ai_candidates_changed(self, event):
        self._push_candidates()

    def _push_candidates(self):
        """Live, non-destructive preview: only filter-passing candidates
        are drawn (sliding the significance/size spinners back reveals
        the hidden ones); a user-discarded candidate stays visible but
        dimmed. Original indices are kept so discard clicks land on the
        right candidate."""
        analysis = self.object.roi_analysis
        self._roi_layer.set_candidates(
            [
                (
                    index,
                    *candidate.geometry_for(analysis.ai_output_kind),
                    candidate.discarded,
                )
                for index, candidate in enumerate(analysis.ai_candidates)
                if candidate.passes(
                    analysis.ai_significance, analysis.ai_min_size, analysis.ai_max_size
                )
            ]
        )

    def _on_ball_radius_dragged(self, radius):
        """The guide was resized on the canvas: that IS the setting, so
        it goes straight to the session and the spinner follows."""
        ball = self.object.roi_analysis.session.ball
        radius = int(round(radius))
        # The trait is a Range; anything outside it would raise rather
        # than clamp, and a drag can reach either end.
        low, high = ROLLING_BALL_RADIUS_BOUNDS_PX
        ball.radius_px = max(min(radius, high), low)

    def _push_scale(self):
        """One path for a session swap and a fresh calibration."""
        scale = self.object.roi_analysis.session.scale
        self.control.set_scale(scale.metres_per_pixel)

    def _on_scale_line_drawn(self, length_px):
        """Ask what the line measures, store the calibration on the
        session, and remember it as the seed for the next experiment."""
        analysis = self.object.roi_analysis
        scale = analysis.session.scale
        entry = ScaleEntry(value=scale.value or 1.0, unit=scale.unit)
        calibration = None
        if entry.edit_traits().result:
            calibration = metres_per_pixel(length_px, entry.value, entry.unit)
        if calibration is not None:
            scale.trait_set(
                metres_per_pixel=calibration, value=entry.value, unit=entry.unit
            )
            preferences = self.object.preferences
            preferences.last_scale_metres_per_px = calibration
            preferences.last_scale_unit = entry.unit
            self._push_scale()
        analysis.interaction_mode = "pan"

    def _on_interaction_mode_changed(self, event):
        mode = event.new
        self._roi_layer.set_mode(mode)
        self._scale_layer.set_mode(mode)
        self.control.setDragMode(
            self.control.DragMode.ScrollHandDrag
            if mode == "pan"
            else self.control.DragMode.NoDrag
        )

    def _redraw(self):
        """Wrap the controller's ready 8-bit frame: the only per-frame
        work left on the GUI thread."""
        display = self.object.display_frame

        if display is None:
            self._pixmap_item.setPixmap(QPixmap())
            return

        self._pixmap_item.setPixmap(QPixmap.fromImage(frame_to_qimage(display)))
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

    def _on_hover(self, x, y):
        # The shown frame: what the cursor is over, and what is measured.
        array = self.object.corrected_array
        if array is None:
            return
        height, width = array.shape[:2]
        if 0 <= x < width and 0 <= y < height:
            self.object.pixel_text = f"({x}, {y}) = {array[y, x]}"
        else:
            self.object.pixel_text = ""
        # Also drawn on the canvas itself, bottom-right (the scale
        # bar's HUD style).
        self.control.set_pixel_text(self.object.pixel_text)


class ImageCanvasEditor(BasicEditorFactory):
    """Factory for the image canvas over the model's ``array`` trait."""

    klass = _ImageCanvasEditor


# Compact icon row above the image: browse/navigate/playback plus the
# position and folder-info readouts.
buttons_group = HGroup(
    UItem(
        "directory_button",
        editor=IconButtonEditor(
            glyph=ICON_FOLDER_OPEN,
            tooltip="Choose the image folder (defaults to the experiment's "
            "raw captures)",
        ),
    ),
    UItem(
        "home_button",
        editor=IconButtonEditor(
            glyph=ICON_HOME,
            tooltip="Back to the current experiment's captures (newest image)",
        ),
    ),
    UItem(
        "open_folder_button",
        editor=IconButtonEditor(
            glyph=ICON_OPEN_IN_NEW,
            tooltip="Open the shown images' folder in the file browser",
        ),
    ),
    # zoom settings
    "12",
    UItem(
        "fit_button",
        editor=IconButtonEditor(glyph=ICON_REFRESH, tooltip="Fit image to the pane"),
    ),
    UItem(
        "zoom_in_button",
        editor=IconButtonEditor(glyph="zoom_in", tooltip="Zoom in one step"),
    ),
    UItem(
        "zoom_out_button",
        editor=IconButtonEditor(glyph="zoom_out", tooltip="Zoom out one step"),
    ),
    # image navigation
    "12",
    UItem(
        "previous_button",
        editor=IconButtonEditor(glyph=ICON_PREVIOUS, tooltip="Previous image"),
    ),
    UItem(
        "playing",
        editor=IconToggleEditor(
            on_glyph=ICON_PAUSE,
            off_glyph=ICON_PLAY,
            tooltip="Cycle through the folder's images",
        ),
    ),
    UItem(
        "next_button", editor=IconButtonEditor(glyph=ICON_NEXT, tooltip="Next image")
    ),
    # The workhorse actions — run the plot, save the data, start the ROI
    # set over — as their own cluster right of the folder buttons.
    "12",
    UItem(
        "object.roi_analysis.calculate_button",
        editor=IconButtonEditor(
            glyph=ICON_SHOW_CHART,
            tooltip="Calculate ROI intensities across the "
            "filtered images and plot them",
        ),
    ),
    UItem(
        "object.roi_analysis.reset_cache_button",
        editor=IconButtonEditor(
            glyph=ICON_RESET_WRENCH,
            tooltip="Reset calculated intensities (optionally "
            "also the drift overrides)",
        ),
    ),
    UItem(
        "object.roi_analysis.export_csv_button",
        editor=IconButtonEditor(
            glyph=ICON_SAVE,
            tooltip="Export the intensities to the experiment's "
            "analysis folder (calculates first if "
            "needed)",
        ),
    ),
    UItem(
        "object.roi_analysis.clear_rois_button",
        editor=IconButtonEditor(glyph=ICON_DELETE_SWEEP, tooltip="Remove all ROIs"),
    ),
    UItem("position_text", style="readonly"),
    # Takes the row's leftover width so the cluster gaps above stay at
    # their fixed 12 px (the numeric spacers are growable Minimum
    # spacer items). The image summary itself lives in the pane title.
    spring,
)


# Collapsible sections (fluorescence controls pane parity): an arrow glyph
# header toggles each bordered group's `show_*` trait.
def _collapse_header(trait, label):
    return HGroup(
        UItem(trait, editor=IconToggleEditor()),
        Label(label),
    )


# Experiment layer (collapsed by default): browse another experiment's
# captures without hunting for its folder — pick it and the viewer repoints
# there, then the image-group / session / image levels reload under it.
experiments_group = VGroup(
    Item(
        "selected_experiment",
        label="Experiment",
        editor=HoverScrollEnumEditor(values_name="experiment_names"),
        tooltip="Browse another experiment's captures (repoints the viewer "
        "at that experiment; use Home to return to the ongoing one)",
    ),
    Item(
        "experiment_number",
        label="Experiment Seek",
        editor=RangeEditor(
            low=1, high_name="object.max_experiment_number", mode="slider"
        ),
        tooltip="Drag through the experiments, oldest to newest",
    ),
    visible_when="show_experiments",
    show_border=True,
)

# Image Group layer: the Image Group is the type subfolder an image sits in
# (e.g. 16bit_raw; "None" for images saved outside one), and captures land
# one session folder per capture run — so pick the type, then the session,
# then the image within it.
bursts_group = VGroup(
    Item(
        "selected_image_group",
        label="Image Group",
        editor=HoverScrollEnumEditor(values_name="image_group_names"),
        tooltip="Pick the image type: the subfolder the captures sit in "
        "('All' spans every type; 'None' holds images saved directly "
        "into a session or the captures folder)",
    ),
    Item(
        "selected_burst",
        label="Capture Session",
        editor=HoverScrollEnumEditor(values_name="burst_names"),
        tooltip="Pick a capture session (one folder per session; "
        "'ungrouped' holds captures outside any session folder)",
    ),
    Item(
        "burst_number",
        label="Session Seek",
        editor=RangeEditor(low=1, high_name="object.max_burst_number", mode="slider"),
        tooltip="Drag through the capture sessions, oldest to newest",
    ),
    visible_when="show_bursts",
    show_border=True,
)

images_group = VGroup(
    # A plain grid row so it aligns with the rows below; the controller
    # retitles "Filter" to the contributed filter's name.
    Item(
        "selected_filter",
        label="Filter",
        editor=HoverScrollEnumEditor(values_name="filter_names"),
        tooltip="Show only captures with one value of this filter "
        "(detected from the filenames)",
        visible_when="image_filter is not None",
    ),
    Item(
        "selected_image",
        label="Image",
        editor=HoverScrollEnumEditor(values_name="image_names"),
        tooltip="Pick an image from the selected capture session",
    ),
    Item(
        "image_number",
        label="Seek",
        editor=RangeEditor(low=1, high_name="object.max_image_number", mode="slider"),
        tooltip="Drag through the capture session's images",
    ),
    visible_when="show_images",
    show_border=True,
)

# Which images the ROI analysis skips: the shown one, or every image on
# one side of it.
exclusion_group = VGroup(
    Item(
        "object.roi_analysis.current_image_excluded",
        label="Exclude current image from analysis",
        tooltip="Ignore the shown image in the ROI calculations "
        "(stats batch, plot, export, drift tracking). Viewing "
        "and ROI drawing on it still work; the mark is saved "
        "with the experiment.",
    ),
    VGroup(
        Label("Exclude all images:"),
        UItem(
            "object.roi_analysis.exclude_before_button",
            tooltip="Exclude every image before the shown one from the analysis",
        ),
        UItem(
            "object.roi_analysis.exclude_after_button",
            tooltip="Exclude every image after the shown one from the analysis",
        ),
        Label("Include all images:"),
        UItem(
            "object.roi_analysis.include_before_button",
            tooltip="Clear the exclusion mark from every image before the shown one",
        ),
        UItem(
            "object.roi_analysis.include_after_button",
            tooltip="Clear the exclusion mark from every image after the shown one",
        ),
        columns=3,
    ),
    visible_when="show_exclusion",
    show_border=True,
)

contrast_group = VGroup(
    Item(
        "auto_contrast",
        label="Auto contrast",
        tooltip="Window the displayed intensities to the 0.1–99.9 "
        "percentile range (raw 16-bit frames are nearly "
        "black without it); uncheck to set the window "
        "manually",
    ),
    Item(
        "window_min",
        label="Min",
        enabled_when="not auto_contrast",
        tooltip="Intensity displayed as black",
    ),
    Item(
        "window_max",
        label="Max",
        enabled_when="not auto_contrast",
        tooltip="Intensity displayed as white",
    ),
    visible_when="show_contrast",
    show_border=True,
)

# ROI analysis: draw/edit tools, then the calculate -> plot -> export
# pipeline over the filtered images, as an always-visible vertical
# toolbar on the image's right edge. Instant/live per-ROI stats show in
# the plot pane's table; batch progress shares the status row under the
# image.
analysis_toolbar = VGroup(
    UItem(
        "object.roi_analysis.draw_ellipse_button",
        editor=IconModeButtonEditor(
            glyph=ICON_CIRCLE,
            mode="draw_ellipse",
            tooltip="Draw an elliptical ROI (click-drag from its "
            "centre; the grip makes it an ellipse). Stays "
            "armed for the next one — Esc puts it away",
        ),
    ),
    UItem(
        "object.roi_analysis.draw_box_button",
        editor=IconModeButtonEditor(
            glyph=ICON_RECTANGLE,
            mode="draw_box",
            tooltip="Draw a rectangular ROI (click-drag on the "
            "image). Stays armed for the next one — Esc "
            "puts it away",
        ),
    ),
    UItem(
        "object.roi_analysis.draw_capsule_button",
        editor=IconModeButtonEditor(
            glyph=ICON_CAPSULE,
            mode="draw_capsule",
            tooltip="Draw a capsule ROI (click-drag its axis, then "
            "use the grip for its radius). Stays armed "
            "for the next one — Esc puts it away",
        ),
    ),
    UItem(
        "object.roi_analysis.draw_polygon_button",
        editor=IconModeButtonEditor(
            glyph=ICON_CONTOUR,
            mode="draw_polygon",
            tooltip="Draw a contour ROI (click to place nodes; "
            "close on the first node, double-click, or "
            "Enter — Esc cancels, Backspace undoes). Stays "
            "armed for the next one — a second Esc puts "
            "it away",
        ),
    ),
    "12",  # measurement toggles
    UItem(
        "object.roi_analysis.calibrate_scale_button",
        editor=IconModeButtonEditor(
            glyph=ICON_RULER,
            mode="draw_scale",
            tooltip="Set the image scale: drag a line of known "
            "length, then type what it measures",
        ),
    ),
    UItem(
        "object.roi_analysis.rolling_ball_enabled",
        editor=IconToggleEditor(
            on_glyph=ICON_TONALITY,
            off_glyph=ICON_TONALITY,
            tooltip="Rolling-ball background correction: flattens "
            "uneven illumination out of every frame before "
            "the ROIs are measured. While it is on, the "
            "image below shows the corrected frame, so what "
            "you see is what is measured.",
        ),
    ),
    UItem(
        "object.roi_analysis.session.ball.show_reference",
        editor=IconToggleEditor(
            on_glyph=ICON_ADJUST,
            off_glyph=ICON_ADJUST,
            tooltip="Draw the ball on the image at its true size, to "
            "hold against the droplets it has to clear. Drag "
            "the circle to move it, or its grip to set the "
            "radius by eye.",
        ),
        enabled_when="object.roi_analysis.rolling_ball_enabled",
    ),
    UItem(
        "object.roi_analysis.define_perspective_button",
        editor=IconButtonEditor(
            glyph=ICON_VIEW_3D,
            tooltip="Define a perspective correction: click four points "
            "on the image, then drag them to where they belong",
        ),
    ),
    UItem(
        "object.roi_analysis.perspective_enabled",
        editor=IconToggleEditor(
            on_glyph=ICON_TRANSFORM,
            off_glyph=ICON_TRANSFORM,
            tooltip="Apply the perspective correction: every image is "
            "warped before it is shown or measured, so the ROIs and "
            "the analysis work on the corrected frames",
        ),
        enabled_when="object.roi_analysis.perspective_defined",
    ),
    UItem(
        "object.roi_analysis.show_background_ring",
        editor=IconToggleEditor(
            on_glyph=ICON_CROP,
            off_glyph=ICON_CROP,
            tooltip="Show the background ring each ROI's correction is measured from",
        ),
    ),
    "12",  # select/edit the existing ROIs
    UItem(
        "object.roi_analysis.edit_mode",
        editor=IconToggleEditor(
            on_glyph=ICON_EDIT,
            off_glyph=ICON_EDIT,
            tooltip="Edit ROIs: drag to move, bottom-right grip to "
            "resize (Shift keeps an ellipse circular), "
            "top-left grip to rotate (Shift snaps to 15°), "
            "pink top-right grip to round a box's corners, "
            "drag a node to reshape a contour, click to "
            "select. Editing on a later image adds a drift "
            "override from there on",
        ),
    ),
    # Delete-selected sits directly under the edit toggle: selecting
    # (edit mode) and deleting the selection are one motion.
    UItem(
        "object.roi_analysis.delete_roi_button",
        editor=IconButtonEditor(
            glyph=ICON_DELETE, tooltip="Delete the selected ROI (Del)"
        ),
    ),
    UItem(
        "object.roi_analysis.copy_roi_button",
        editor=IconButtonEditor(
            glyph=ICON_COPY, tooltip="Copy the selected ROI's shape (Ctrl+C)"
        ),
    ),
    UItem(
        "object.roi_analysis.paste_roi_button",
        editor=IconButtonEditor(
            glyph=ICON_PASTE,
            tooltip="Paste the copied shape as a new ROI, offset "
            "from the original (Ctrl+V)",
        ),
    ),
    "12",  # AI tools
    UItem(
        "object.roi_analysis.ai_pick_button",
        editor=IconModeButtonEditor(
            glyph="wand_shine",
            mode="ai_pick",
            tooltip="AI picker: click a droplet and the model "
            "segments it into an ROI. Stays armed — Esc "
            "puts it away. Install via Help > Install AI "
            "ROI Support if disabled.",
        ),
        enabled_when="analysis.ai_available",
    ),
    UItem(
        "object.roi_analysis.ai_detect_button",
        editor=IconButtonEditor(
            glyph="eye_tracking",
            tooltip="Detect all droplets on this frame (AI grid "
            "sweep). Results appear as dashed candidates: "
            "click to discard, then Accept. Install via "
            "Help > Install AI ROI Support if disabled.",
        ),
        enabled_when="analysis.ai_available",
    ),
    UItem(
        "object.roi_analysis.ai_track_button",
        editor=IconButtonEditor(
            glyph="ink_highlighter_move",
            tooltip="Track the ROIs across later frames (drift). "
            "Press again to stop; finished frames are "
            "kept. Install via Help > Install AI ROI "
            "Support if disabled.",
        ),
        enabled_when="analysis.ai_available",
    ),
    # Takes the column's stretch so the cluster gaps above stay at
    # their fixed 12 px instead of spreading down the pane (the fixed
    # spacers are growable Minimum spacer items).
    spring,
)

# Selector sidebar: the five collapsible sections stacked, hidden as one
# unit by the chevron toggle (device-viewer sidebar parity).
sidebar_group = VGroup(
    _collapse_header("show_experiments", "Experiments"),
    experiments_group,
    _collapse_header("show_bursts", "Image Groups"),
    bursts_group,
    _collapse_header("show_images", "Images"),
    images_group,
    _collapse_header("show_exclusion", "Analysis Exclusion"),
    exclusion_group,
    _collapse_header("show_contrast", "Contrast"),
    contrast_group,
    visible_when="show_sidebar",
)

# The measurement settings, under the image they act on: the background
# ring around each ROI, the rolling ball over the whole frame, and the
# scale/pixel readouts. They live here rather than with the plot because
# they decide what is measured, and because the canvas above shows their
# effect as they are dragged.
correction_group = Group(
    # auto_set: a typed value must reach the session before Calculate
    # reads it, or the batch finds nothing missing and reports "up to
    # date" against the old ring.
    Item(
        "object.roi_analysis.session.ring.gap_px",
        label="Ring Gap",
        editor=RangeEditor(
            low=RING_GAP_BOUNDS_PX[0],
            high=RING_GAP_BOUNDS_PX[1],
            mode="spinner",
            auto_set=True,
        ),
        tooltip="Pixels between an ROI's edge and the ring its "
        "background is read from. Fluorescence bleeds a pixel "
        "or two past the boundary and that halo is not "
        "background.",
    ),
    Item(
        "object.roi_analysis.session.ring.thickness_px",
        label="Ring Width",
        editor=RangeEditor(
            low=RING_THICKNESS_BOUNDS_PX[0],
            high=RING_THICKNESS_BOUNDS_PX[1],
            mode="spinner",
            auto_set=True,
        ),
        tooltip="Thickness of the background ring, in pixels. "
        "Changing either value recomputes the statistics.",
    ),
    Item(
        "object.roi_analysis.session.ball.radius_px",
        label="Ball Radius",
        editor=RangeEditor(
            low=ROLLING_BALL_RADIUS_BOUNDS_PX[0],
            high=ROLLING_BALL_RADIUS_BOUNDS_PX[1],
            mode="spinner",
            auto_set=True,
        ),
        enabled_when="object.roi_analysis.rolling_ball_enabled",
        tooltip="Ball radius in pixels — the scale of the unevenness "
        "removed. Keep it comfortably larger than the "
        "droplets, or the ball rolls over them and takes the "
        "signal too. The image shows the result as you drag.",
    ),
    Item(
        "zoom_step",
        label="Zoom Step",
        editor=DoubleSpinBoxEditor(
            low=IMAGE_ZOOM_STEP_BOUNDS[0],
            high=IMAGE_ZOOM_STEP_BOUNDS[1],
            decimals=2,
            step=0.05,
        ),
        tooltip="How much one mouse-wheel notch zooms the image "
        "canvas (zooming out uses the reciprocal). 1.05 is "
        "barely perceptible; 2.0 doubles per notch.",
    ),
    label="Measurement",
    show_border=True,
    columns=3,
)

# AI (SAM) detection options: significance/size filters over the last
# pick/detect/track pass's candidates, the shape accepted candidates
# become, and the drift re-check interval, plus Accept/Clear over the
# pending candidates. Hidden with the rest of the AI surface when the
# optional SAM stack is not installed.
ai_group = Group(
    Item(
        "object.roi_analysis.ai_significance",
        label="Significance",
        editor=RangeEditor(low=1, high=20, mode="spinner", auto_set=True),
        tooltip="Significance: how many grid points independently "
        "produced a candidate during Detect all. Clear "
        "droplets score 2-4, one-off noise 1; click-added "
        "ROIs are exempt. Non-destructive: sliding back "
        "reveals hidden candidates.",
    ),
    # The size window's spinners bound each other (magnet z-stage
    # preferences parity): min cannot pass max, max cannot dip under
    # min — the editors' live limits track the opposite trait.
    Item(
        "object.roi_analysis.ai_min_size",
        label="Min Size",
        editor=RangeEditor(
            low=0,
            high_name="object.roi_analysis.ai_max_size",
            mode="spinner",
            auto_set=True,
        ),
        tooltip="Hide candidates whose mean ellipse diameter (px) "
        "is below this. Applies to all candidates.",
    ),
    Item(
        "object.roi_analysis.ai_max_size",
        label="Max Size",
        editor=RangeEditor(
            low_name="object.roi_analysis.ai_min_size",
            high=AI_SIZE_FILTER_CEILING_PX,
            mode="spinner",
            auto_set=True,
        ),
        tooltip="Hide candidates whose mean ellipse diameter (px) "
        "is above this. Applies to all candidates.",
    ),
    Item(
        "object.roi_analysis.ai_output_kind",
        label="Output Shape",
        tooltip="Shape an accepted candidate becomes: the traced "
        "polygon outline, or the fitted ellipse.",
    ),
    Item(
        "object.roi_analysis.ai_drift_interval",
        label="Drift Interval",
        editor=RangeEditor(low=1, high=50, mode="spinner", auto_set=True),
        tooltip="Track drift: re-segment every Nth frame (the "
        "final frame always); skipped frames inherit. "
        "Larger N = faster tracking for slow drift.",
    ),
    HGroup(
        UItem(
            "object.roi_analysis.ai_accept_button",
            editor=IconButtonEditor(
                glyph=ICON_SAVE, tooltip="Accept the filter-passing candidates as ROIs"
            ),
            visible_when="analysis.ai_accept_count > 0",
        ),
        UItem(
            "object.roi_analysis.ai_clear_button",
            editor=IconButtonEditor(
                glyph=ICON_CANCEL, tooltip="Discard all candidates"
            ),
            visible_when="len(analysis.ai_candidates) > 0",
        ),
    ),
    label="AI Detection",
    show_border=True,
    columns=3,
    visible_when="analysis.ai_available",
)

# The measurement and AI grids as one collapsible block under the image.
advanced_settings_group = VGroup(
    HGroup(UItem("scale_text", style="readonly")),
    correction_group,
    ai_group,
    visible_when="show_advanced_settings",
)

ImageViewerView = View(
    HGroup(
        VGroup(
            UItem(
                "show_sidebar",
                editor=IconToggleEditor(
                    on_glyph=ICON_CHEVRON_LEFT,
                    off_glyph=ICON_CHEVRON_RIGHT,
                    tooltip="Hide or show the selector sidebar",
                ),
            )
        ),
        HSplit(
            sidebar_group,
            VGroup(
                buttons_group,
                UItem(
                    "array", editor=ImageCanvasEditor(), springy=True, resizable=True
                ),
                # The measurement + AI option rows are advanced
                # settings: one chevron collapses them together.
                _collapse_header("show_advanced_settings", "Advanced"),
                advanced_settings_group,
                HGroup(
                    UItem(
                        "object.roi_analysis.progress_text",
                        editor=ProgressReadoutEditor(),
                    ),
                ),
            ),
        ),
        analysis_toolbar,
    ),
    # Scrollable so the dock can be dragged to any size: the toolbars and
    # setting grids keep their natural size and scroll once the pane is
    # smaller than them, while the canvas (minimum 1x1) still takes all
    # the room the pane has to spare.
    resizable=True,
    scrollable=True,
)
