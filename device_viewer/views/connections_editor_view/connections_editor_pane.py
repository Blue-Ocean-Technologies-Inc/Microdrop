# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Edit Connections dialog, as TraitsUI MVC: the device SVG rendered
alone with a dot on every electrode centroid, where the user drags lines
between dots to add connections on top of the generated ones, and
selects and deletes existing connections.

Qt stays in the canvas (ConnectionsCanvasView + ConnectionsOverlay,
embedded through a CustomEditor); the header row around it is traits.
Every edit lands on the SVG model straight away, so the main device view
redraws and Save writes the Connections layer — the dialog has nothing
to confirm."""

# Enthought library imports.
from pyface.qt.QtCore import QRectF
from pyface.qt.QtGui import QImage, QPixmap
from traits.api import (
    Bool,
    Button,
    Float,
    HasTraits,
    Instance,
    Property,
    Str,
    observe,
)
from traitsui.api import CustomEditor, HGroup, UItem, VGroup, View, spring

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_DELETE,
    ICON_FIT_SCREEN,
    ICON_VISIBILITY,
    ICON_VISIBILITY_OFF,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import IconButtonEditor, IconToggleEditor

# Local imports.
from ...models.connections_editor import ConnectionsEditorModel
from ..camera_alignment_view.alignment_panes import (
    CANVAS_MIN_SIZE_PX,
    HEADER_TITLE_STYLE_SHEET,
)
from .connections_canvas import ConnectionsCanvasView
from .connections_overlay import ConnectionsOverlay

#: The window's opening size.
START_WIDTH_PX = 1000
START_HEIGHT_PX = 720

CONNECTIONS_EDITOR_INSTRUCTIONS = (
    "Drag from one electrode's dot to another's to connect them — the "
    "line snaps onto the dots. Click a line to select it (Ctrl-click for "
    "several, Shift-drag for a box) and press Delete to remove it. "
    "Scroll to zoom, drag the image to pan."
)


def _canvas_factory(parent, editor):
    """CustomEditor factory: embed the pane's canvas widget."""
    return editor.object.canvas


connections_editor_view = View(
    VGroup(
        HGroup(
            UItem(
                "title",
                style="readonly",
                tooltip=CONNECTIONS_EDITOR_INSTRUCTIONS,
            ),
            spring,
            UItem(
                "show_centroids",
                editor=IconToggleEditor(
                    on_glyph=ICON_VISIBILITY,
                    off_glyph=ICON_VISIBILITY_OFF,
                    tooltip="Show the electrode centroid dots",
                ),
            ),
            UItem(
                "fit",
                editor=IconButtonEditor(
                    glyph=ICON_FIT_SCREEN, tooltip="Fit the device in the view"
                ),
            ),
            UItem(
                "delete_selected",
                editor=IconButtonEditor(
                    glyph=ICON_DELETE, tooltip="Delete the selected connections"
                ),
                enabled_when="has_selection",
            ),
            style_sheet=HEADER_TITLE_STYLE_SHEET,
        ),
        UItem("canvas", editor=CustomEditor(_canvas_factory), springy=True),
    ),
    title="Edit Connections",
    width=START_WIDTH_PX,
    height=START_HEIGHT_PX,
    resizable=True,
)


class ConnectionsEditorPane(HasTraits):
    """The dialog's pane: header row over the canvas. Builds the canvas
    and its overlay from the rendered device image, then keeps the
    overlay and the model in step."""

    model = Instance(ConnectionsEditorModel)

    #: The device SVG rendered alone.
    device_image = Instance(QImage)
    #: The device-scene rect the image covers.
    scene_rect = Instance(QRectF)
    #: SVG-unit -> device-scene scale (``ElectrodeLayer.path_scale``);
    #: with ``scene_rect`` it carries the electrode centroids into the
    #: canvas's image pixels.
    path_scale = Float(1.0)
    device_name = Str()

    #: Header title.
    title = Str()

    #: The zoomable QGraphics canvas the overlay lives on.
    canvas = Instance(ConnectionsCanvasView)

    show_centroids = Bool(True)
    #: Refit the image in the view.
    fit = Button()
    delete_selected = Button()

    #: Top-level mirror of the model's selection for ``enabled_when``,
    #: which does not follow nested traits.
    has_selection = Property(Bool, observe="model.selected_connections.items")

    _overlay = Instance(ConnectionsOverlay)

    traits_view = connections_editor_view

    def traits_init(self):
        self.title = (
            f"Connections — {self.device_name}" if self.device_name else "Connections"
        )

        canvas = ConnectionsCanvasView(QPixmap.fromImage(self.device_image))
        canvas.setMinimumSize(*CANVAS_MIN_SIZE_PX)
        canvas.delete_requested.connect(self.model.remove_selected)
        self.canvas = canvas

        self._overlay = ConnectionsOverlay(
            canvas.scene(),
            self._centroids_in_image(),
            on_connection_drawn=self.model.svg_model.add_connection,
            on_selection_changed=self._on_lines_selected,
        )
        canvas.overlay = self._overlay

        self._overlay.set_connections(self.model.svg_model.connections)
        self._overlay.set_centroids_visible(self.show_centroids)

    # ------------------------------------------------------------------ #
    def _get_has_selection(self):
        return bool(self.model.selected_connections)

    def _centroids_in_image(self):
        """Electrode id -> centroid in the canvas's image pixels."""
        rect = self.scene_rect
        x_scale = self.device_image.width() / rect.width()
        y_scale = self.device_image.height() / rect.height()

        return {
            electrode_id: (
                (self.path_scale * x - rect.x()) * x_scale,
                (self.path_scale * y - rect.y()) * y_scale,
            )
            for electrode_id, (x, y) in self.model.svg_model.electrode_centers.items()
        }

    def _on_lines_selected(self, electrode_id_pairs):
        self.model.selected_connections = electrode_id_pairs

    # ------------------------------------------------------------------ #
    @observe("model:svg_model:connections")
    def _on_connections_changed(self, event):
        self._overlay.set_connections(event.new)

    @observe("show_centroids")
    def _on_show_centroids_changed(self, event):
        # A constructor-supplied value arrives before traits_init has
        # built the overlay; traits_init applies that one itself.
        if self._overlay is not None:
            self._overlay.set_centroids_visible(event.new)

    def _fit_fired(self):
        self.canvas.fit_frame()

    def _delete_selected_fired(self):
        self.model.remove_selected()
