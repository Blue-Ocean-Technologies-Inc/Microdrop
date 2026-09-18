# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""SCRATCH SPIKE — the one Qt piece: a device canvas that tints every wide
path's footprint (one colour) with its route on top and, for the selected
path, fills the current phase in white. Click or drag across electrodes to
extend the selected path's route (revisits make loops and knots), drag from
empty space to pan, wheel to zoom, Esc to clear."""

# Third-party imports.
from shapely.geometry import Point
from shapely.ops import unary_union

# Enthought library imports.
from pyface.qt.QtCore import QPointF, Qt
from pyface.qt.QtGui import (
    QBrush,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from pyface.qt.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
)
from traits.api import Callable, HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.views.zone_view.zone_region_item import (
    make_selection_highlight_item,
    shapely_geometry_to_painter_path,
)

# Local imports.
from .consts import CLICK_DRAG_THRESHOLD_PX, ELECTRODE_FILL_COLOR
from .models import WidePathDemoModel

LANE_Z, SECTION_Z, LINE_Z = 0.8, 0.85, 0.9

CENTRE_COLOR = "#ffee58"
HEAD_COLOR = "#66bb6a"
SLUG_COLOR = "#4fc3f7"


def cosmetic_pen(color, width, style=Qt.PenStyle.SolidLine):
    pen = QPen(QColor(color))
    pen.setCosmetic(True)
    pen.setWidth(width)
    pen.setStyle(style)
    return pen


class _CanvasRedrawBridge(HasTraits):
    """Qt-free observer wiring: model changes -> canvas repaint callbacks.
    Kept separate from the QGraphicsView so the traits observation graph
    never holds Qt objects."""

    model = Instance(WidePathDemoModel)
    redraw_paths = Callable
    rebuild_electrodes = Callable

    @observe(
        "[model:paths.items, model:paths:items:phases, "
        "model:selected_index, model:step]"
    )
    def _paths_changed(self, event):
        self.redraw_paths()

    @observe("model:electrode_polygons")
    def _device_changed(self, event):
        self.rebuild_electrodes()


class WidePathCanvas(QGraphicsView):
    """The device view. Owns scene painting and mouse interaction only;
    every edit goes through ``WidePathModel.pick`` on the selected path."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.model = model
        self._path_items = []
        self._press_view_pos = None
        self._drawing = False
        self._escape_window = None
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._bridge = _CanvasRedrawBridge(
            model=model,
            redraw_paths=self._redraw_paths,
            rebuild_electrodes=self._rebuild_electrodes,
        )
        self._rebuild_electrodes()

    # ---------------------------------------------------------------- device
    def _rebuild_electrodes(self):
        self.scene().clear()
        self._path_items = []
        for polygon in self.model.electrode_polygons.values():
            item = QGraphicsPathItem(shapely_geometry_to_painter_path(polygon, 1.0))
            item.setBrush(QBrush(QColor(ELECTRODE_FILL_COLOR)))
            item.setPen(QPen(Qt.PenStyle.NoPen))
            self.scene().addItem(item)
        self.scene().setSceneRect(self.scene().itemsBoundingRect())
        self.resetTransform()
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._redraw_paths()

    def _electrode_under(self, view_pos):
        scene_pos = self.mapToScene(view_pos)
        point = Point(scene_pos.x(), scene_pos.y())
        for electrode_id, polygon in self.model.electrode_polygons.items():
            if polygon.contains(point):
                return electrode_id
        return None

    def _union(self, electrode_ids):
        polygons = self.model.electrode_polygons
        members = [polygons[i] for i in electrode_ids if i in polygons]
        return unary_union(members) if members else None

    # ----------------------------------------------------------- interaction
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_view_pos = event.pos()
            # A press on an electrode starts drawing; on empty space, a pan.
            self._drawing = (
                self.model.selected is not None
                and self._electrode_under(event.pos()) is not None
            )
            if not self._drawing:
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing and event.buttons() & Qt.MouseButton.LeftButton:
            electrode_id = self._electrode_under(event.pos())
            path = self.model.selected
            # A sweep extends the route with every neighbour it crosses;
            # revisits are fine (loops, knots), only a non-neighbour is not.
            if electrode_id is not None and (
                not path.route_ids
                or electrode_id in path.electrode_neighbours.get(path.route_ids[-1], [])
            ):
                path.pick(electrode_id)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        is_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_view_pos is not None
            and (event.pos() - self._press_view_pos).manhattanLength()
            < CLICK_DRAG_THRESHOLD_PX
        )
        self._press_view_pos = None
        if event.button() == Qt.MouseButton.LeftButton:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        if is_click and self._drawing:
            electrode_id = self._electrode_under(event.pos())
            if electrode_id is not None:
                self.model.selected.pick(electrode_id)
        self._drawing = False

    def wheelEvent(self, event):
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)

    def showEvent(self, event):
        super().showEvent(event)
        if self._escape_window is not self.window():
            self._escape_window = self.window()
            self._wire_escape_shortcut()

    def _wire_escape_shortcut(self):
        # TraitsUI's dialog owns a window-wide Escape shortcut; piggyback on
        # it rather than register an ambiguous second one (see the zones
        # demo canvas for the full story).
        escape = QKeySequence(Qt.Key.Key_Escape)
        for shortcut in self._escape_window.findChildren(QShortcut):
            if shortcut.key() == escape:
                shortcut.activated.connect(self._handle_escape)
                return
        shortcut = QShortcut(escape, self._escape_window)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._handle_escape)

    def _handle_escape(self):
        self.model.escape_pressed = True

    # -------------------------------------------------------------- painting
    def _redraw_paths(self):
        for item in self._path_items:
            self.scene().removeItem(item)
        self._path_items = []
        for path in self.model.paths:
            self._draw_path(path, path is self.model.selected)

    def _draw_path(self, path, is_selected):
        if not path.route_ids:
            return
        add = self._add_path_item

        # Everything the slug ever touches, one colour; the route on top.
        footprint = self._union(path.footprint_ids)
        if footprint is not None:
            add(make_selection_highlight_item(footprint, 1.0, SLUG_COLOR), LANE_Z)
        route = self._union(path.route_ids)
        if route is not None:
            add(make_selection_highlight_item(route, 1.0, CENTRE_COLOR), LANE_Z)

        phases = path.phases
        if is_selected and phases:
            ids = phases[min(self.model.step, len(phases) - 1)].ids
            geometry = self._union(ids)
            if geometry is not None:
                box = QGraphicsPathItem(shapely_geometry_to_painter_path(geometry, 1.0))
                box.setPen(cosmetic_pen("#ffffff", 3))
                box.setBrush(QBrush(QColor(255, 255, 255, 70)))
                add(box, SECTION_Z)

        centroids = [path.centroids[i] for i in path.route_ids]
        polyline = QPainterPath(QPointF(*centroids[0]))
        for x, y in centroids[1:]:
            polyline.lineTo(x, y)
        line_item = QGraphicsPathItem(polyline)
        line_item.setPen(cosmetic_pen(CENTRE_COLOR, 3 if is_selected else 1))
        add(line_item, LINE_Z)
        radius = path.pitch * 0.12
        for index, (x, y) in enumerate(centroids):
            dot = QGraphicsEllipseItem(x - radius, y - radius, 2 * radius, 2 * radius)
            dot.setBrush(QBrush(QColor("#ffffff" if index else HEAD_COLOR)))
            dot.setPen(QPen(Qt.PenStyle.NoPen))
            add(dot, LINE_Z)

    def _add_path_item(self, item, z_value):
        item.setZValue(z_value)
        self.scene().addItem(item)
        self._path_items.append(item)


def wide_path_canvas_factory(parent, editor):
    return WidePathCanvas(editor.object)
