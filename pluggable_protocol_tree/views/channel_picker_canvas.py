# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The channel picker's device picture, as a TraitsUI editor.

``ChannelPickerCanvas`` is raw Qt — TraitsUI has no editor for a clickable,
zoomable vector picture: the electrode polygons, each labelled with its
channel, with the current entry's channels lit. ``ChannelPickerCanvasEditor``
wraps it for a ``ChannelPickerModel``: it follows the model's current
channels and its zoom / fit / rotate requests, and turns clicks into
``toggle_channel`` calls.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import observe
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

# Microdrop style imports.
from microdrop_style.colors import ACCENT_COLOR, BLACK, GREY, WHITE

# Local imports.
from ..models.channel_picker_model import ZOOM_STEP_FACTOR

#: Item data role holding an electrode polygon's id.
_ELECTRODE_ID_ROLE = 0

#: Channel label size as a fraction of its electrode's smaller side.
_LABEL_FRACTION = 0.45

#: Scene margin around the device, as a fraction of its larger side.
_SCENE_MARGIN_FRACTION = 0.03

#: Smallest size the canvas shrinks to, in pixels.
CANVAS_MIN_SIZE_PX = (320, 240)


class ChannelPickerCanvas(QtWidgets.QGraphicsView):
    """Electrode polygons with channel labels; reports the channel of a
    clicked electrode. Wheel zooms, dragging off the pickable electrodes
    pans."""

    channel_clicked = QtCore.Signal(int)

    def __init__(self, electrode_paths, electrode_channels, parent=None):
        super().__init__(parent)
        self._electrode_channels = electrode_channels
        self._polygons = {}
        self._labels = {}

        #: True once the user zoomed; resizes then keep their framing.
        self._user_zoomed = False

        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setMinimumSize(*CANVAS_MIN_SIZE_PX)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setBackgroundBrush(QtGui.QColor(WHITE))
        self.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

        self._draw_device(electrode_paths)

    # --- drawing ---

    def _draw_device(self, electrode_paths):
        scene = self.scene()
        pen = QtGui.QPen(QtGui.QColor(GREY["dark"]))
        pen.setCosmetic(True)

        for electrode_id, vertices in electrode_paths.items():
            if len(vertices) < 3:
                continue

            polygon = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in vertices])
            item = scene.addPolygon(polygon, pen)
            item.setData(_ELECTRODE_ID_ROLE, electrode_id)
            self._polygons[electrode_id] = item

            channel = self._electrode_channels.get(electrode_id)

            if channel is not None:
                # Qt shows an item's cursor on hover: only pickable
                # electrodes get the pointing hand.
                item.setCursor(QtCore.Qt.PointingHandCursor)
                self._labels[electrode_id] = self._add_label(item, channel)

        bounds = scene.itemsBoundingRect()
        margin = max(bounds.width(), bounds.height()) * _SCENE_MARGIN_FRACTION
        scene.setSceneRect(bounds.adjusted(-margin, -margin, margin, margin))

    @staticmethod
    def _add_label(polygon_item, channel):
        """Channel number centred on its electrode, scaled to fit inside;
        it turns about its own centre to stay upright as the view rotates."""
        label = QtWidgets.QGraphicsSimpleTextItem(str(channel), polygon_item)
        bounds = polygon_item.boundingRect()
        text_bounds = label.boundingRect()

        scale = (
            _LABEL_FRACTION
            * min(bounds.width(), bounds.height())
            / max(text_bounds.width(), text_bounds.height())
        )
        label.setTransformOriginPoint(text_bounds.center())
        label.setScale(scale)
        label.setPos(bounds.center() - text_bounds.center())

        return label

    def show_channels(self, channels):
        """Light the electrodes on ``channels``; channel-less ones stay grey."""
        selected = set(channels)

        for electrode_id, item in self._polygons.items():
            channel = self._electrode_channels.get(electrode_id)

            if channel is None:
                fill, text = GREY["lighter"], BLACK
            elif channel in selected:
                fill, text = ACCENT_COLOR, WHITE
            else:
                fill, text = GREY["lightest"], BLACK

            item.setBrush(QtGui.QColor(fill))

            if electrode_id in self._labels:
                self._labels[electrode_id].setBrush(QtGui.QColor(text))

    # --- framing ---

    def set_rotation(self, degrees):
        """Turn the picture clockwise by ``degrees`` and refit it; labels
        counter-rotate so the channel numbers stay readable."""
        self.resetTransform()
        self.rotate(degrees)

        for label in self._labels.values():
            label.setRotation(-degrees)

        self.fit_device()

    def fit_device(self):
        """Frame the whole device at the current rotation."""
        self._user_zoomed = False
        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def zoom(self, factor):
        self._user_zoomed = True
        self.scale(factor, factor)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_device()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if not self._user_zoomed:
            self.fit_device()

    def wheelEvent(self, event):
        zoom_in = event.angleDelta().y() > 0
        self.zoom(ZOOM_STEP_FACTOR if zoom_in else 1 / ZOOM_STEP_FACTOR)
        event.accept()

    # --- picking ---

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())

        # A click on a channel label belongs to the electrode under it.
        while item is not None and item.data(_ELECTRODE_ID_ROLE) is None:
            item = item.parentItem()

        channel = (
            None
            if item is None
            else self._electrode_channels.get(item.data(_ELECTRODE_ID_ROLE))
        )
        is_left = event.button() == QtCore.Qt.LeftButton

        if is_left and channel is not None:
            self.channel_clicked.emit(channel)
            event.accept()

            return

        # Anywhere else a left drag pans — only for that drag, so the cursor
        # stays an arrow while picking.
        if is_left:
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)


class _ChannelPickerCanvasEditor(QtEditor):
    """Binds a ``ChannelPickerCanvas`` to the ``ChannelPickerModel`` being
    edited (``object``); the observers drop off when the editor is
    disposed and ``object`` is cleared."""

    def init(self, parent):
        model = self.object
        self.control = ChannelPickerCanvas(
            model.electrode_paths, model.electrode_channels
        )
        self.control.channel_clicked.connect(model.toggle_channel)
        self.control.set_rotation(model.rotation)
        self.control.show_channels(model.current_channels)

    def update_editor(self):
        """The edited trait is only the canvas's anchor; the observers below
        carry every change."""

    @observe("object:current_channels")
    def _show_current_entry(self, event):
        self.control.show_channels(event.new)

    @observe("object:rotation")
    def _rotate_device(self, event):
        self.control.set_rotation(event.new)

    @observe("object:zoom_requested")
    def _zoom_device(self, event):
        self.control.zoom(event.new)

    @observe("object:fit_requested")
    def _fit_device(self, event):
        self.control.fit_device()


class ChannelPickerCanvasEditor(BasicEditorFactory):
    """Factory for the channel picker's device picture::

    UItem("electrode_paths", editor=ChannelPickerCanvasEditor())
    """

    klass = _ChannelPickerCanvasEditor
