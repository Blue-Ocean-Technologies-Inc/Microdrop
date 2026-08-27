# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The two camera-alignment panes of the combined Camera Alignment
dialog, as TraitsUI MVC:

- EndpointPane — the device SVG rendered alone, where the user
  places the per-device alignment endpoint (scene coordinates).
- OutlinePane — one captured camera frame, where the user marks the
  device outline by hand (camera pixels), with a recapture glyph to
  grab a fresh frame without reopening anything.

Qt stays in the canvas (ZoomPanImageView + QuadOverlay, embedded
through a CustomEditor); everything around it — the bold title
carrying the usage instructions as its tooltip, the glyph buttons,
the no-frame warning, readiness — is traits, laid out declaratively.
Both panes show the orange endpoint-style quad (conspicuous corner
dots) over the zoomable canvas, and both expose pane-level
snap-radius and appearance setters the dialog's settings sidebar
drives live. The panes carry no commit buttons of their own beyond
the per-pane save glyph — the dialog's single Confirm Alignment
button drives both by firing their ``save`` traits."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPixmap
from traits.api import (
    Bool,
    Button,
    Callable,
    Dict,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Str,
    Tuple,
    Union,
    observe,
)
from traitsui.api import CustomEditor, HGroup, UItem, VGroup, View, spring

from logger.logger_service import get_logger
from microdrop_style.colors import WARNING_COLOR
from microdrop_style.icons.icons import (
    ICON_FIT_SCREEN,
    ICON_PHOTO_CAMERA,
    ICON_SAVE,
    ICON_VISIBILITY,
    ICON_VISIBILITY_OFF,
)
from microdrop_utils.traitsui_qt_helpers import (
    HtmlLabelEditor,
    IconButtonEditor,
    IconToggleEditor,
)

from ...utils.image_corners import detect_corner_points
from .quad_overlay import QuadOverlay
from .zoom_pan_view import ZoomPanImageView

logger = get_logger(__name__)

#: The placeholder canvas shown before the camera delivers a frame.
PLACEHOLDER_SIZE_PX = (640, 480)
CANVAS_MIN_SIZE_PX = (320, 240)

HEADER_TITLE_STYLE_SHEET = "QLabel { font-weight: bold; }"
NO_FRAME_WARNING_TEMPLATE = (
    f'<span style="color: {WARNING_COLOR}; ' 'font-weight: bold;">{}</span>'
)

ENDPOINT_INSTRUCTIONS = (
    "The orange frame is this device's alignment endpoint — where "
    "the camera feed's marked points land on Go To Endpoint. Drag "
    "the corner dots to adjust it. Scroll to zoom, drag the image "
    "to pan."
)
OUTLINE_INSTRUCTIONS = (
    "Drag the four corner dots onto the device's corners — they "
    "snap onto corners detected in the image. Scroll to zoom, drag "
    "the image to pan."
)


def _canvas_factory(parent, editor):
    """CustomEditor factory: embed the pane's canvas widget."""
    return editor.object.canvas


def _valid_quad(quad):
    """``quad`` when it is a well-formed 4-point list, else None."""
    return quad if quad and len(quad) == 4 else None


class AlignmentPaneBase(HasTraits):
    """One alignment pane: a header row (bold title carrying the
    usage instructions as its tooltip, plus glyph buttons) over the
    zoomable canvas with the orange quad. Subclasses build the
    canvas and overlay in ``traits_init`` and implement
    ``_save_fired`` (fire ``save`` to commit programmatically)."""

    #: Header title.
    title = Str()

    #: The zoomable QGraphics canvas the quad overlay lives on.
    canvas = Instance(ZoomPanImageView)

    #: QuadOverlay styling/snap kwargs (snap_radius_px,
    #: handle_radius_px, frame_width_px and the colors) applied to
    #: the overlay at creation and updatable live via
    #: set_snap_radius/set_appearance.
    overlay_options = Dict()

    #: Show every corner the dragged dots can snap onto.
    show_snap_points = Bool(False)

    #: Refit the image in the view.
    fit = Button()
    #: Commit just this pane (the dialog's Confirm Alignment fires
    #: both panes' ``save``).
    save = Button()

    _overlay = Instance(QuadOverlay)

    # ------------------------------------------------------------------ #
    def set_snap_radius(self, snap_radius_px):
        self.overlay_options["snap_radius_px"] = snap_radius_px
        if self._overlay is not None:
            self._overlay.set_snap_radius(snap_radius_px)

    def set_appearance(self, **kwargs):
        """Forward QuadOverlay.set_appearance kwargs, remembered so
        an overlay created later (first recapture) picks them up."""
        self.overlay_options.update(kwargs)
        if self._overlay is not None:
            self._overlay.set_appearance(**kwargs)

    # ------------------------------------------------------------------ #
    def _header_group(self, instructions, *action_items):
        """The header row: bold title (usage instructions as its
        tooltip), then the glyph buttons."""
        return HGroup(
            UItem("title", style="readonly", tooltip=instructions),
            spring,
            UItem(
                "show_snap_points",
                editor=IconToggleEditor(
                    on_glyph=ICON_VISIBILITY,
                    off_glyph=ICON_VISIBILITY_OFF,
                    tooltip="Show every corner the dots can snap onto",
                ),
            ),
            UItem(
                "fit",
                editor=IconButtonEditor(
                    glyph=ICON_FIT_SCREEN, tooltip="Fit the image in the view"
                ),
            ),
            *action_items,
            style_sheet=HEADER_TITLE_STYLE_SHEET,
        )

    def _install_canvas(self, pixmap):
        canvas = ZoomPanImageView(pixmap)
        canvas.setMinimumSize(*CANVAS_MIN_SIZE_PX)
        self.canvas = canvas

    def _create_overlay(self, quad, snap_points):
        self._overlay = QuadOverlay(
            self.canvas.scene(), quad, snap_points=snap_points, **self.overlay_options
        )
        if self.show_snap_points:
            self._overlay.set_snap_markers_visible(True)

    @observe("show_snap_points")
    def _show_snap_points_changed(self, event):
        if self._overlay is not None:
            self._overlay.set_snap_markers_visible(event.new)

    def _fit_fired(self):
        self.canvas.fit_frame()

    @staticmethod
    def _default_quad(pixmap) -> list:
        """A centered half-image box to start from when there is no
        previous quad to show."""
        width, height = pixmap.width(), pixmap.height()
        return [
            [width * 0.25, height * 0.25],
            [width * 0.75, height * 0.25],
            [width * 0.75, height * 0.75],
            [width * 0.25, height * 0.75],
        ]


class EndpointPane(AlignmentPaneBase):
    """View and edit one device's alignment endpoint over a render
    of just that device's SVG. Save only emits — nothing here moves
    the live alignment; the owner persists the endpoint."""

    #: The device SVG rendered alone.
    device_image = Instance(QImage)
    #: The device-scene rect the image covers — the linear
    #: image-pixel <-> scene-coordinate bridge, so the quad
    #: round-trips exactly into 'Go To Endpoint' targets.
    scene_rect = Instance(QRectF)
    #: The saved endpoint to start from, if any.
    initial_scene_quad = Union(None, List())
    device_name = Str()
    #: Optional device-scene corner points (electrode path
    #: vertices) the dragged dots snap onto.
    snap_scene_points = List()

    #: Fires on save with the endpoint quad in DEVICE SCENE
    #: coordinates ([[x, y] * 4], TL/TR/BR/BL as placed).
    endpoint_saved = Event()

    _pixmap_size = Tuple(Int(), Int())

    def traits_init(self):
        self.title = (
            f"Endpoint — {self.device_name}" if self.device_name else "Endpoint"
        )
        pixmap = QPixmap.fromImage(self.device_image)
        self._pixmap_size = (max(pixmap.width(), 1), max(pixmap.height(), 1))
        self._install_canvas(pixmap)

        quad = _valid_quad(self.initial_scene_quad)
        quad = (
            [self._scene_to_image(point) for point in quad]
            if quad
            else self._default_quad(pixmap)
        )
        snap_points = (
            [self._scene_to_image(point) for point in self.snap_scene_points]
            if self.snap_scene_points
            else None
        )
        self._create_overlay(quad, snap_points)

    def default_traits_view(self):
        return View(
            VGroup(
                self._header_group(
                    ENDPOINT_INSTRUCTIONS,
                    UItem(
                        "save",
                        editor=IconButtonEditor(
                            glyph=ICON_SAVE, tooltip="Save just this device's endpoint"
                        ),
                    ),
                ),
                UItem("canvas", editor=CustomEditor(_canvas_factory), springy=True),
            ),
        )

    # ------------------------------------------------------------------ #
    def _scene_to_image(self, point) -> list:
        width, height = self._pixmap_size
        rect = self.scene_rect
        return [
            (float(point[0]) - rect.x()) / max(rect.width(), 1e-9) * width,
            (float(point[1]) - rect.y()) / max(rect.height(), 1e-9) * height,
        ]

    def _image_to_scene(self, point) -> list:
        width, height = self._pixmap_size
        rect = self.scene_rect
        return [
            rect.x() + float(point[0]) / width * rect.width(),
            rect.y() + float(point[1]) / height * rect.height(),
        ]

    def _save_fired(self):
        """Emit the placed endpoint in device-scene coordinates."""
        self.endpoint_saved = [
            self._image_to_scene(point) for point in self._overlay.quad()
        ]


class OutlinePane(AlignmentPaneBase):
    """Mark the device outline on a captured camera frame, by hand.
    The user IS the detector — but the dots snap onto corner
    features detected on the frame (Shi-Tomasi, sub-pixel)."""

    #: Zero-arg callable returning a fresh camera QImage, or None
    #: when the camera has no frame. Called once at construction and
    #: again on every recapture click.
    capture_frame = Callable()
    #: The current alignment quad to start from, if any.
    initial_quad = Union(None, List())

    #: True once a real frame (and thus the quad) exists — gates the
    #: save glyph here and Confirm Alignment in the dialog.
    is_ready = Bool(False)

    #: Grab a fresh frame from the camera.
    recapture = Button()

    #: Fires on save with the quad in CAMERA pixels
    #: ([[x, y] * 4], TL/TR/BR/BL as placed).
    quad_accepted = Event()

    #: Shown until the first real frame arrives: without it a black
    #: canvas gives no clue what went wrong.
    no_frame_warning = Str(
        "No camera frame — is the camera on? Press the camera glyph "
        "above to capture one."
    )

    def traits_init(self):
        self.title = "Device Outline"
        image = self.capture_frame() if self.capture_frame else None
        if image is not None and not image.isNull():
            pixmap = QPixmap.fromImage(image)
            self._install_canvas(pixmap)
            self._create_overlay(
                _valid_quad(self.initial_quad) or self._default_quad(pixmap),
                detect_corner_points(image),
            )
            self.is_ready = True
        else:
            # No frame yet (camera off?) — a black placeholder plus
            # the visible warning until the recapture glyph delivers
            # one.
            placeholder = QPixmap(*PLACEHOLDER_SIZE_PX)
            placeholder.fill(Qt.black)
            self._install_canvas(placeholder)

    def default_traits_view(self):
        return View(
            VGroup(
                self._header_group(
                    OUTLINE_INSTRUCTIONS,
                    UItem(
                        "recapture",
                        editor=IconButtonEditor(
                            glyph=ICON_PHOTO_CAMERA,
                            tooltip="Recapture — grab a fresh frame " "from the camera",
                        ),
                    ),
                    UItem(
                        "save",
                        editor=IconButtonEditor(
                            glyph=ICON_SAVE,
                            tooltip="Use just these outline points "
                            "(stage them on the feed)",
                        ),
                        enabled_when="is_ready",
                    ),
                ),
                UItem(
                    "no_frame_warning",
                    editor=HtmlLabelEditor(template=NO_FRAME_WARNING_TEMPLATE),
                    visible_when="not is_ready",
                ),
                UItem("canvas", editor=CustomEditor(_canvas_factory), springy=True),
            ),
        )

    # ------------------------------------------------------------------ #
    def _recapture_fired(self):
        """Grab a fresh frame: swap the canvas image and re-detect
        the snap corners, leaving an already-placed quad where the
        user put it."""
        image = self.capture_frame() if self.capture_frame else None
        if image is None or image.isNull():
            logger.warning(
                "outline recapture: nothing to capture " "— the camera has no frame"
            )
            return
        pixmap = QPixmap.fromImage(image)
        self.canvas.set_pixmap(pixmap)
        snap_points = detect_corner_points(image)
        if self._overlay is not None:
            self._overlay.set_snap_points(snap_points)
        else:
            # First real frame after the placeholder: the pane
            # becomes usable now (the warning hides itself and the
            # save glyph enables through is_ready).
            self._create_overlay(
                _valid_quad(self.initial_quad) or self._default_quad(pixmap),
                snap_points,
            )
            self.canvas.fit_frame()
            self.is_ready = True

    def _save_fired(self):
        """Emit the marked outline quad in camera pixels."""
        if self._overlay is None:
            return
        self.quad_accepted = self._overlay.quad()
