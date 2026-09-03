# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Scene items for electrode zones: one filled path per committed region,
plus the dashed highlight used for the pending selection."""

# Enthought library imports.
from pyface.qt.QtCore import QPointF, Qt
from pyface.qt.QtGui import QColor, QPainterPath, QPen, QPolygonF
from pyface.qt.QtWidgets import QGraphicsPathItem

# Local imports.
from ...consts import (
    ZONE_FILL_OPACITY,
    ZONE_OUTLINE_PEN_WIDTH,
    ZONE_PENDING_Z_VALUE,
    ZONE_REGION_Z_VALUE,
)


def shapely_geometry_to_painter_path(geometry, scale):
    """Polygon or MultiPolygon (SVG coords) -> QPainterPath in scene coords
    (``scale`` is ElectrodeLayer.path_scale), holes included."""
    painter_path = QPainterPath()
    for polygon in getattr(geometry, "geoms", [geometry]):
        for ring in [polygon.exterior, *polygon.interiors]:
            painter_path.addPolygon(
                QPolygonF([QPointF(x * scale, y * scale) for x, y in ring.coords])
            )
            painter_path.closeSubpath()
    return painter_path


class ZoneRegionItem(QGraphicsPathItem):
    """Filled, outlined union outline of one committed region."""

    def __init__(
        self,
        region,
        geometry,
        scale,
        color,
        alpha,
        outline_pen_width=ZONE_OUTLINE_PEN_WIDTH,
        z_value=ZONE_REGION_Z_VALUE,
    ):
        super().__init__(shapely_geometry_to_painter_path(geometry, scale))
        self.region = region
        fill_color = QColor(color)
        fill_color.setAlphaF(alpha * ZONE_FILL_OPACITY)
        self.setBrush(fill_color)
        outline_pen = QPen(QColor(color))
        outline_pen.setCosmetic(True)
        outline_pen.setWidth(outline_pen_width)
        self.setPen(outline_pen)
        self.setZValue(z_value)

    def shape(self):
        # Hit-test the fill only: the cosmetic pen's stroke is huge in item
        # coordinates and would register clicks far outside the region.
        return self.path()


def make_selection_highlight_item(geometry, scale, color):
    """Dashed, semi-transparent highlight over a set of electrodes (the
    pending selection or a live rubber-band capture)."""
    highlight_item = QGraphicsPathItem(
        shapely_geometry_to_painter_path(geometry, scale)
    )
    fill_color = QColor(color)
    fill_color.setAlphaF(ZONE_FILL_OPACITY)
    highlight_item.setBrush(fill_color)
    highlight_pen = QPen(QColor(color))
    highlight_pen.setCosmetic(True)
    highlight_pen.setWidth(ZONE_OUTLINE_PEN_WIDTH)
    highlight_pen.setStyle(Qt.PenStyle.DashLine)
    highlight_item.setPen(highlight_pen)
    highlight_item.setZValue(ZONE_PENDING_Z_VALUE)
    highlight_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    return highlight_item
