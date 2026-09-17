# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The connections editor's graphics: a dot on every electrode centroid,
one selectable line per connection, and the line being dragged out from
one centroid towards another — managed as one unit on a QGraphicsScene,
like the camera-alignment QuadOverlay whose snapping it shares."""

# Third-party imports.
import numpy as np

# Enthought library imports.
from pyface.qt.QtCore import QLineF, QPointF, Qt
from pyface.qt.QtGui import QColor, QPen
from pyface.qt.QtWidgets import QGraphicsItem, QGraphicsLineItem, QStyle

# Local imports.
from ...consts import (
    ALIGNMENT_SNAP_MARKER_ALPHA,
    ALIGNMENT_SNAP_MARKER_COLOR_HEX,
    CONNECTIONS_EDITOR_CENTROID_SIZE_PX,
    CONNECTIONS_EDITOR_GRAB_RADIUS_PX,
    CONNECTIONS_EDITOR_LINE_COLOR_HEX,
    CONNECTIONS_EDITOR_LINE_WIDTH_PX,
    CONNECTIONS_EDITOR_PENDING_LINE_COLOR_HEX,
    CONNECTIONS_EDITOR_SELECTED_LINE_COLOR_HEX,
    CONNECTIONS_EDITOR_SELECTED_LINE_WIDTH_PX,
    CONNECTIONS_EDITOR_SNAP_RADIUS_PX,
)
from ...utils.snapping import nearest_point_index_within, scene_view_scale
from ..camera_alignment_view.quad_overlay import SnapPointMarkersItem


class ConnectionLineItem(QGraphicsLineItem):
    """One connection, selectable. Selection shows as the selected pen
    rather than Qt's dashed bounding box."""

    def __init__(self, key, start, end, pen, selected_pen):
        super().__init__(QLineF(start, end))
        #: The (electrode id, electrode id) pair this line connects.
        self.key = key
        self._pen = pen
        self._selected_pen = selected_pen

        self.setPen(pen)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.setPen(self._selected_pen if self.isSelected() else self._pen)

        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.State_Selected
        super().paint(painter, option, widget)


class ConnectionsOverlay:
    """The centroid dots, the connection lines and the pending line."""

    def __init__(
        self,
        scene,
        centroids,
        on_connection_drawn,
        on_selection_changed,
        z_value=50.0,
    ):
        """``centroids``: electrode id -> (x, y) scene point.
        ``on_connection_drawn`` fires with the two electrode ids when a
        line is dragged from one centroid onto another;
        ``on_selection_changed`` with the selected lines' id pairs."""
        self._scene = scene
        self._on_connection_drawn = on_connection_drawn
        self._on_selection_changed = on_selection_changed
        self._z_value = z_value

        self._electrode_ids = list(centroids)
        self._points = np.asarray(list(centroids.values()), dtype=float)

        self._line_items = []
        #: Index of the centroid the pending line starts from; None
        #: while no line is being drawn.
        self._pending_start = None

        self._line_pen = self._cosmetic_pen(
            CONNECTIONS_EDITOR_LINE_COLOR_HEX, CONNECTIONS_EDITOR_LINE_WIDTH_PX
        )
        self._selected_line_pen = self._cosmetic_pen(
            CONNECTIONS_EDITOR_SELECTED_LINE_COLOR_HEX,
            CONNECTIONS_EDITOR_SELECTED_LINE_WIDTH_PX,
        )

        self._markers = SnapPointMarkersItem(
            self._points,
            ALIGNMENT_SNAP_MARKER_COLOR_HEX,
            ALIGNMENT_SNAP_MARKER_ALPHA,
            marker_px=CONNECTIONS_EDITOR_CENTROID_SIZE_PX,
        )
        # The dots are hit-tested by distance (begin_line), never by
        # Qt — their one big item must not swallow presses.
        self._markers.setAcceptedMouseButtons(Qt.NoButton)
        self._markers.setZValue(z_value + 1)
        scene.addItem(self._markers)

        self._pending_line = QGraphicsLineItem()
        self._pending_line.setPen(
            self._cosmetic_pen(
                CONNECTIONS_EDITOR_PENDING_LINE_COLOR_HEX,
                CONNECTIONS_EDITOR_SELECTED_LINE_WIDTH_PX,
            )
        )
        self._pending_line.setZValue(z_value + 2)
        self._pending_line.setVisible(False)
        scene.addItem(self._pending_line)

        scene.selectionChanged.connect(self._selection_changed)

    # ------------------------------------------------------------------ #
    def set_connections(self, electrode_id_pairs):
        """Replace the lines; a pair given in both directions draws
        once."""
        for item in self._line_items:
            self._scene.removeItem(item)

        self._line_items = []
        drawn = set()

        for from_id, to_id in electrode_id_pairs:
            if frozenset((from_id, to_id)) in drawn:
                continue

            drawn.add(frozenset((from_id, to_id)))
            item = ConnectionLineItem(
                (from_id, to_id),
                self._centroid(self._electrode_ids.index(from_id)),
                self._centroid(self._electrode_ids.index(to_id)),
                self._line_pen,
                self._selected_line_pen,
            )
            item.setZValue(self._z_value)

            self._scene.addItem(item)
            self._line_items.append(item)

    def set_centroids_visible(self, visible):
        self._markers.setVisible(bool(visible))

    # ------------------------- drawing a line ------------------------- #
    def begin_line(self, scene_pos):
        """Start a line from the centroid under ``scene_pos``; False
        when the press is not on one."""
        self._pending_start = self._centroid_index_near(
            scene_pos, CONNECTIONS_EDITOR_GRAB_RADIUS_PX
        )

        if self._pending_start is None:
            return False

        start = self._centroid(self._pending_start)
        self._pending_line.setLine(QLineF(start, start))
        self._pending_line.setVisible(True)

        return True

    def update_line(self, scene_pos):
        """Drag the pending line's free end, snapped onto any other
        centroid in reach."""
        end = self._snap_target(scene_pos)

        self._pending_line.setLine(
            QLineF(
                self._centroid(self._pending_start),
                scene_pos if end is None else self._centroid(end),
            )
        )

    def finish_line(self, scene_pos):
        """Drop the pending line; on another centroid it becomes a
        connection, anywhere else it is discarded."""
        end = self._snap_target(scene_pos)
        start = self._pending_start

        self._pending_start = None
        self._pending_line.setVisible(False)

        if end is not None:
            self._on_connection_drawn(
                self._electrode_ids[start], self._electrode_ids[end]
            )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _cosmetic_pen(color, width_px):
        pen = QPen(QColor(color), width_px)
        pen.setCosmetic(True)  # constant width at any zoom
        pen.setCapStyle(Qt.RoundCap)

        return pen

    def _centroid(self, index):
        return QPointF(*self._points[index])

    def _centroid_index_near(self, scene_pos, radius_px):
        return nearest_point_index_within(
            self._points,
            scene_pos.x(),
            scene_pos.y(),
            radius_px / scene_view_scale(self._scene),
        )

    def _snap_target(self, scene_pos):
        """Index of the centroid the pending line's free end snaps
        onto — never the one it started from."""
        end = self._centroid_index_near(scene_pos, CONNECTIONS_EDITOR_SNAP_RADIUS_PX)

        return None if end == self._pending_start else end

    def _selection_changed(self):
        self._on_selection_changed(
            [
                item.key
                for item in self._scene.selectedItems()
                if isinstance(item, ConnectionLineItem)
            ]
        )
