# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsScene

from pyface.qt.QtCore import QPointF, Qt
from pyface.qt.QtWidgets import QGraphicsRectItem

from device_viewer.models.main_model import DeviceViewMainModel

from microdrop_utils.pyside_helpers import get_qcolor_lighter_percent_from_factor

from ...consts import (
    ZONE_BAND_Z_VALUE,
    ZONE_OUTLINE_PEN_WIDTH,
    ZONE_SELECTED_OUTLINE_PEN_WIDTH,
    ZONE_SUBTRACT_PREVIEW_COLOR,
)
from ...default_settings import (
    CONNECTION_LINE_OFF,
    ELECTRODE_CHANNEL_EDITING,
    ELECTRODE_DISABLED,
    ELECTRODE_NO_CHANNEL,
    ELECTRODE_OFF,
    ELECTRODE_ON,
    PERSPECTIVE_RECT_COLOR,
    PERSPECTIVE_RECT_COLOR_EDITING,
    ROUTE_CCW_LOOP,
    ROUTE_CW_LOOP,
    ROUTE_SELECTED,
    actuated_electrodes_key,
    connections_key,
    electrode_fill_key,
    electrode_outline_key,
    electrode_text_key,
    hovered_actuation_key,
    hovered_electrode_key,
    routes_key,
    zones_key,
)
from ..zone_view.zone_region_item import ZoneRegionItem, make_selection_highlight_item
from .electrode_view_helpers import loop_is_ccw
from .electrodes_view_base import (
    ElectrodeConnectionItem,
    ElectrodeEndpointItem,
    ElectrodeView,
)

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ElectrodeLayer:
    """
    Class defining the view for an electrode layer in the device viewer.
    Container for the elements used to establish the device viewer scene.

    - This view contains a group of electrode view objects
    - The view is responsible for updating the properties of all the
      electrode views contained in bulk.
    """

    def __init__(self, electrodes, default_alphas: dict[int, float]):
        # Create the connection and electrode items
        self.connection_items = {}
        self.electrode_views = {}
        self.electrode_endpoints = {}
        self.reference_rect_item = None
        self.reference_rect_path_item = None

        # Zone overlay: region id -> ZoneRegionItem, plus the transient
        # pending-selection highlight and rubber-band rectangle.
        self.zone_items = {}
        self.zone_pending_item = None
        self.zone_band_item = None
        self.zone_move_ghost_item = None

        self.svg = electrodes.svg_model

        # # Scale to approx 360p resolution for display
        modifier = max(
            640 / (self.svg.max_x - self.svg.min_x),
            360 / (self.svg.max_y - self.svg.min_y),
        )
        #: SVG-path -> scene coordinate scale: every view below is
        #: built from ``modifier * path``, so anything comparing raw
        #: electrode paths against scene positions must apply this.
        self.path_scale = modifier

        # Create the electrode views for each electrode from the electrodes
        # model and add them to the group
        for electrode_id, electrode in electrodes.electrodes.items():
            self.electrode_views[electrode_id] = ElectrodeView(
                electrode_id,
                electrodes[electrode_id],
                modifier * electrode.path,
                default_alphas=default_alphas,
            )
            self.electrode_endpoints[electrode_id] = ElectrodeEndpointItem(
                electrode_id,
                QPointF(
                    self.svg.electrode_centers[electrode_id][0] * modifier,
                    self.svg.electrode_centers[electrode_id][1] * modifier,
                ),
                8,
            )

        # Create the connections between the electrodes
        connections = {
            key: (
                QPointF(coord1[0] * modifier, coord1[1] * modifier),
                QPointF(coord2[0] * modifier, coord2[1] * modifier),
            )
            for key, (coord1, coord2) in self.svg.connections.items()
            # key here is form dmf_utils.SvgUtil (see neighbours_to_points),
            # and is a tuple of 2 electrode_ids. if (id1, id2) exists in the
            # dict, then (id2, id1) wont, and viice versa
        }

        for key, (src, dst) in connections.items():
            self.connection_items[key] = ElectrodeConnectionItem(key, src, dst)

    ################# add electrodes/connections from scene #################
    def add_electrodes_to_scene(self, parent_scene: "QGraphicsScene"):
        for electrode_id, electrode_view in self.electrode_views.items():
            parent_scene.addItem(electrode_view)
        # Promote labels to top-level items above every electrode: as
        # children they are painted over by later-added sibling electrodes
        # wherever a label overhangs its own shape. ElectrodeViews sit at
        # the origin, so the labels' coordinates are already scene coords.
        for electrode_view in self.electrode_views.values():
            electrode_view.text_path.setParentItem(None)
            electrode_view.text_path.setZValue(1)
            parent_scene.addItem(electrode_view.text_path)

    def add_connections_to_scene(self, parent_scene: "QGraphicsScene"):
        """
        Method to draw the connections between the electrodes in the layer
        """
        for key, item in self.connection_items.items():
            parent_scene.addItem(item)

    def add_endpoints_to_scene(self, parent_scene: "QGraphicsScene"):
        for electrode_id, endpoint_view in self.electrode_endpoints.items():
            parent_scene.addItem(endpoint_view)

    def add_zones_to_scene(self, parent_scene: "QGraphicsScene"):
        """Exists for symmetry with ``remove_zones_to_scene``: re-adds any
        zone region items already built but not currently in the scene."""
        for item in self.zone_items.values():
            if item.scene() is None:
                parent_scene.addItem(item)

    ######################## remove electrodes/connections from scene ########
    def remove_electrodes_to_scene(self, parent_scene: "QGraphicsScene"):
        for electrode_id, electrode_view in self.electrode_views.items():
            parent_scene.removeItem(electrode_view.text_path)
            parent_scene.removeItem(electrode_view)

    def remove_connections_to_scene(self, parent_scene: "QGraphicsScene"):
        """
        Method to draw the connections between the electrodes in the layer
        """
        for key, item in self.connection_items.items():
            parent_scene.removeItem(item)

    def remove_endpoints_to_scene(self, parent_scene: "QGraphicsScene"):
        for electrode_id, endpoint_view in self.electrode_endpoints.items():
            parent_scene.removeItem(endpoint_view)

    def remove_zones_to_scene(self, parent_scene: "QGraphicsScene"):
        for item in self.zone_items.values():
            parent_scene.removeItem(item)
        self.zone_items = {}
        self._remove_zone_pending(parent_scene)
        self.hide_zone_band(parent_scene)
        self.hide_zone_move_ghost(parent_scene)

    def _remove_zone_pending(self, parent_scene):
        if self.zone_pending_item is not None:
            parent_scene.removeItem(self.zone_pending_item)
            self.zone_pending_item = None

    ######### catch all methods to add / remove all elements from scene ######
    def add_all_items_to_scene(self, parent_scene: "QGraphicsScene"):
        self.add_electrodes_to_scene(parent_scene)
        self.add_connections_to_scene(parent_scene)
        self.add_endpoints_to_scene(parent_scene)
        self.add_zones_to_scene(parent_scene)

        self.reference_rect_item = parent_scene.addPolygon(
            QPolygonF(), QPen(QColor(PERSPECTIVE_RECT_COLOR), 3)
        )

        self.reference_rect_path_item = QGraphicsPathItem()
        self.reference_rect_path_item.setPen(
            QPen(QColor(PERSPECTIVE_RECT_COLOR_EDITING), 2)
        )
        parent_scene.addItem(self.reference_rect_path_item)

    def remove_all_items_to_scene(self, parent_scene: "QGraphicsScene"):
        self.remove_electrodes_to_scene(parent_scene)
        self.remove_connections_to_scene(parent_scene)
        self.remove_endpoints_to_scene(parent_scene)
        self.remove_zones_to_scene(parent_scene)
        parent_scene.removeItem(self.reference_rect_item)

    def toggle_electrode_tooltips(self, checked):
        for electrode_id, electrode_view in self.electrode_views.items():
            electrode_view.toggle_tooltip(checked)

    ######################## Redraw functions ###########################
    def redraw_connections_to_scene(self, model: DeviceViewMainModel):
        # Routes are applied in order, so later routes will apply on top
        # To minimize the number of overlapping Qt calls, we'll apply changes
        # to a dictionary then transfer it to the view at the end

        connection_map = {}  # Temporary map to superimpose routes
        endpoint_map = {}  # Temporary map to superimpose endpoints

        layers = model.routes.layers

        if model.routes.selected_layer:
            layers = layers + [
                model.routes.selected_layer
            ]  # Paint the selected layer again so its always on top

        if model.routes.autoroute_layer:
            layers = layers + [
                model.routes.autoroute_layer
            ]  # Paint autoroute layer on top

        for i in range(len(layers)):
            route_layer = layers[i]
            color = QColor(route_layer.color)
            # Make sure each route is it own layer. Prevents weird overlap patterns
            z = i
            if route_layer == model.routes.selected_layer:
                color = QColor(ROUTE_SELECTED)
            elif route_layer.route.is_loop():
                if loop_is_ccw(route_layer.route, self.svg.electrode_centers):
                    color = QColor(ROUTE_CCW_LOOP)
                else:
                    color = QColor(ROUTE_CW_LOOP)
            if route_layer.visible:
                for endpoint_id in route_layer.route.get_endpoints():
                    endpoint_map[endpoint_id] = (color, z)

                for (
                    route_from,
                    route_to,
                ) in route_layer.route.get_segments():  # Connections
                    connection_map[(route_from, route_to)] = (color, z)

        # Apply map
        alpha = model.get_alpha(routes_key)
        connection_alpha = model.get_alpha(connections_key)

        for key, connection_item in self.connection_items.items():
            (color, z) = connection_map.get(key, (None, None))
            if color:
                connection_item.set_active(color, alpha)
                connection_item.setZValue(
                    z
                )  # We want to make sure the whole route is on the same z value
            elif connection_alpha > 0:
                # Base layer: paint every possible connection in white so
                # users can see where routes can be drawn. z=0 keeps it above
                # the electrode fill (connections are added to the scene
                # after electrodes) yet beneath the coloured route segments.
                # get_alpha returns 0 when this layer is hidden.
                connection_item.set_active(
                    QColor(CONNECTION_LINE_OFF),
                    connection_alpha,
                    width=1,
                    show_arrow=False,
                )
                connection_item.setZValue(0)
            else:
                connection_item.set_inactive()

        for endpoint_id, endpoint_view in self.electrode_endpoints.items():
            (color, z) = endpoint_map.get(endpoint_id, (None, None))
            if color:
                endpoint_view.set_active(color, alpha)
                endpoint_view.setZValue(z)
            else:
                endpoint_view.set_inactive()

    def redraw_electrode_lines(self, model: DeviceViewMainModel):
        """
        Method to redraw the electrode lines in the layer
        """
        alpha = model.get_alpha(electrode_outline_key)
        for electrode_id, electrode_view in self.electrode_views.items():
            electrode_view.update_line_alpha(alpha)

    def recolor_electrode(
        self,
        model: DeviceViewMainModel,
        electrode_view: ElectrodeView,
        electrode_hovered: ElectrodeView,
    ):
        """Recompute one electrode's color stack from the model state.

        ElectrodeView.update_color skips the repaint when the stack is
        value-equal to the current one, so calling this for untouched
        electrodes costs no rendering."""
        # determine base_color:
        if electrode_view.electrode == model.electrodes.electrode_editing:
            base_color = ELECTRODE_CHANNEL_EDITING

        elif electrode_view.electrode.channel is None:
            base_color = ELECTRODE_NO_CHANNEL

        else:
            base_color = ELECTRODE_OFF

        # construct the base QColor
        base_color = QColor(base_color)
        base_color.setAlphaF(model.get_alpha(electrode_fill_key))

        # Determine inner color: disabled (red) takes priority over actuation
        channel = electrode_view.electrode.channel
        is_disabled = channel in model.electrodes.disabled_channels
        if is_disabled != electrode_view._disabled:
            # Tooltips only mention the disabled flag, so they need
            # rebuilding only when it flips — not on every recolor.
            electrode_view._disabled = is_disabled
            electrode_view.update_tooltip()
        inner_color = None
        if is_disabled:
            inner_color = QColor(ELECTRODE_DISABLED)
            inner_color.setAlphaF(model.get_alpha(actuated_electrodes_key))
        elif channel in model.electrodes.actuated_channels:
            inner_color = QColor(ELECTRODE_ON)
            inner_color.setAlphaF(model.get_alpha(actuated_electrodes_key))

        # check if fills need editing if they are hovered:
        if electrode_hovered == electrode_view:
            lighter_percent = get_qcolor_lighter_percent_from_factor(
                base_color, model.get_alpha(hovered_electrode_key)
            )
            base_color = base_color.lighter(lighter_percent)
            if inner_color:
                lighter_percent = get_qcolor_lighter_percent_from_factor(
                    inner_color, model.get_alpha(hovered_actuation_key)
                )
                inner_color = inner_color.lighter(lighter_percent)

        color_stack = [base_color]
        if inner_color:
            color_stack.append(inner_color)

        electrode_view.update_color(color_stack)

    def redraw_electrode_colors(
        self, model: DeviceViewMainModel, electrode_hovered: ElectrodeView
    ):
        for electrode_view in self.electrode_views.values():
            self.recolor_electrode(model, electrode_view, electrode_hovered)

    def redraw_electrode_colors_for_channels(
        self, model: DeviceViewMainModel, channels, electrode_hovered: ElectrodeView
    ):
        """Recolor only the electrodes mapped to ``channels`` — the
        actuation hot path during protocol runs, where each phase changes
        a handful of channels out of the whole board."""
        for channel in channels:
            for electrode_id in model.electrodes.channels_electrode_ids_map.get(
                channel, []
            ):
                electrode_view = self.electrode_views.get(electrode_id)
                if electrode_view is not None:
                    self.recolor_electrode(model, electrode_view, electrode_hovered)

    def redraw_electrode_labels(self, model: DeviceViewMainModel):
        alpha = model.get_alpha(electrode_text_key)
        for electrode_id, electrode_view in self.electrode_views.items():
            electrode_view.update_label(alpha)

    def redraw_reference_rect(self, rect: list[QPointF]):
        if len(rect) == 4:
            # Update the reference rect visualization
            self.reference_rect_item.setPolygon(QPolygonF(rect))
            self.reference_rect_path_item.setVisible(
                False
            )  # Hide the path item if we're using a polygon
            self.reference_rect_item.setVisible(True)  # Show the polygon item

        elif len(rect) > 1:
            path = QPainterPath()
            path.moveTo(rect[0])
            # Draw the path for the reference rect
            for point in rect[1:]:
                path.lineTo(point)
            self.reference_rect_path_item.setPath(path)
            self.reference_rect_path_item.setVisible(True)
            self.reference_rect_item.setVisible(
                False
            )  # Hide the polygon item if we're using a path

        elif len(rect) == 1:
            path = QPainterPath()
            path.addEllipse(rect[0], 4, 4)
            self.reference_rect_path_item.setPath(path)
            self.reference_rect_path_item.setVisible(True)

    def clear_reference_rect(self):
        """Reset the reference rectangle to its initial state."""
        self.reference_rect_item.setPolygon(QPolygonF())
        self.reference_rect_item.setVisible(False)
        self.reference_rect_path_item.setPath(QPainterPath())
        self.reference_rect_path_item.setVisible(False)

    def redraw_electrode_tooltip(self, changed_electrode_id):
        logger.debug(f"redraw_electrode_tooltip: {changed_electrode_id}")
        self.electrode_views[changed_electrode_id].update_tooltip()

    def redraw_all_electrode_tooltips(self):
        logger.debug("redraw_all_electrode_tooltips")
        for changed_electrode_id in self.electrode_views:
            self.redraw_electrode_tooltip(changed_electrode_id)

    def rotate_electrode_views_texts(self, angle=0):
        for electrode_view in self.electrode_views.values():
            electrode_view.rotate_electrode_text(angle)

    def get_electrodes_views_bounding_rect(self) -> "QRectF":
        """
        Calculates the united bounding rectangle of all electrode views
        in the current layer. Returns an empty QRectF if no views exist.
        """
        views = self.electrode_views.values()

        if not views:
            return QRectF()  # Return empty rect if no items

        # Initialize with the first item's rect
        # (This avoids the repeated 'if target_rect is None' check inside the loop)
        iterator = iter(views)
        target_rect = next(iterator).sceneBoundingRect()

        # Unite with the rest
        for view in iterator:
            target_rect = target_rect.united(view.sceneBoundingRect())

        return target_rect

    ######################## Zone redraw functions #######################
    def redraw_zones(self, model: DeviceViewMainModel, parent_scene: "QGraphicsScene"):
        """Rebuild every committed region's item from the manager: hidden
        regions and the one being edited get no item; the selected ones draw
        a thicker outline. Alpha 0 (row hidden) draws nothing."""
        for item in self.zone_items.values():
            parent_scene.removeItem(item)
        self.zone_items = {}
        alpha = model.get_alpha(zones_key)
        if alpha <= 0:
            return
        manager = model.zones
        for region in manager.regions:
            if not region.visible or region is manager.editing_region:
                continue
            zone_type = manager.zone_type_for(region.zone_id)
            geometry = manager.region_outline(region)
            if zone_type is None or geometry is None:
                continue
            pen_width = (
                ZONE_SELECTED_OUTLINE_PEN_WIDTH
                if region in manager.selected_regions
                else ZONE_OUTLINE_PEN_WIDTH
            )
            item = ZoneRegionItem(
                region, geometry, self.path_scale, zone_type.color, alpha, pen_width
            )
            parent_scene.addItem(item)
            self.zone_items[region.id] = item

    def redraw_zone_pending(
        self,
        model: DeviceViewMainModel,
        parent_scene: "QGraphicsScene",
        preview_ids=None,
        subtract=False,
    ):
        """Dashed highlight of the pending selection, folded with a live
        rubber-band capture (``preview_ids`` added, or subtracted when
        ``subtract``)."""
        self._remove_zone_pending(parent_scene)
        manager = model.zones
        electrode_ids = list(manager.pending_electrode_ids)
        if preview_ids:
            if subtract:
                electrode_ids = [i for i in electrode_ids if i not in set(preview_ids)]
            else:
                electrode_ids.extend(i for i in preview_ids if i not in electrode_ids)
        zone_type = manager.zone_type_for(manager.active_zone_id)
        geometry = manager.electrode_union(electrode_ids)
        if zone_type is None or geometry is None:
            return
        color = ZONE_SUBTRACT_PREVIEW_COLOR if subtract else zone_type.color
        self.zone_pending_item = make_selection_highlight_item(
            geometry, self.path_scale, color
        )
        parent_scene.addItem(self.zone_pending_item)

    def show_zone_band(self, parent_scene: "QGraphicsScene", rect):
        """Dashed rubber-band rectangle (scene coords) while dragging."""
        if self.zone_band_item is None:
            self.zone_band_item = QGraphicsRectItem()
            band_pen = QPen(QColor(CONNECTION_LINE_OFF))
            band_pen.setCosmetic(True)
            band_pen.setStyle(Qt.PenStyle.DashLine)
            self.zone_band_item.setPen(band_pen)
            self.zone_band_item.setZValue(ZONE_BAND_Z_VALUE)
            self.zone_band_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            parent_scene.addItem(self.zone_band_item)
        self.zone_band_item.setRect(rect)

    def hide_zone_band(self, parent_scene: "QGraphicsScene"):
        if self.zone_band_item is not None:
            parent_scene.removeItem(self.zone_band_item)
            self.zone_band_item = None

    def show_zone_move_ghost(self, parent_scene: "QGraphicsScene", geometry, color):
        """Dashed copy of the regions being dragged; moved with
        ``move_zone_ghost`` while the pointer travels."""
        self.hide_zone_move_ghost(parent_scene)
        self.zone_move_ghost_item = make_selection_highlight_item(
            geometry, self.path_scale, color
        )
        parent_scene.addItem(self.zone_move_ghost_item)

    def move_zone_ghost(self, delta):
        if self.zone_move_ghost_item is not None:
            self.zone_move_ghost_item.setPos(delta)

    def hide_zone_move_ghost(self, parent_scene: "QGraphicsScene"):
        if self.zone_move_ghost_item is not None:
            parent_scene.removeItem(self.zone_move_ghost_item)
            self.zone_move_ghost_item = None
