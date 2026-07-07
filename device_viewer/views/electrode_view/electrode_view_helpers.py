import numpy as np
from PySide6.QtWidgets import QGraphicsScene
from device_viewer.models.route import Route
from shapely.geometry import LinearRing, Point, Polygon
from shapely.ops import polylabel


def find_path_item(scene: QGraphicsScene, connected_electrodes_keys):
    """Find a QGraphicsPathItem with the exact path sequence"""
    # Local import: electrodes_view_base imports label_geometry from here.
    from .electrodes_view_base import ElectrodeConnectionItem
    for item in scene.items():
        if isinstance(item, ElectrodeConnectionItem):
            if item.key[0] in connected_electrodes_keys and item.key[1] in connected_electrodes_keys:
                return item

    return None  # No match found

def loop_is_ccw(route: Route, electrode_centers: dict[object, tuple[float]]):
    """Determine if a Route is counterclockwise based on position data in electrode_centers"""
    if not route.is_loop():
        raise ValueError(f"route {route} must be a loop")
    coords = list(map(lambda id: electrode_centers[id], route.route))
    ring = LinearRing(coords)
    return ring.is_ccw


def get_mean_path(item):
    return np.mean(item.electrode.path, axis=0)


def label_geometry(path_data: np.ndarray) -> tuple[float, float, float]:
    """Anchor point and available room for an electrode's channel label.

    Returns ``(anchor_x, anchor_y, extent)`` where the anchor is the polygon's
    pole of inaccessibility (the interior point farthest from any edge) and
    extent is the inscribed-circle diameter around it. The bounding-box center
    is wrong for curved/concave electrodes — it can fall outside the shape
    entirely, dropping the label onto a neighbour — and bbox extents oversize
    the font for shapes much thinner than their box. For rectangles this
    reduces exactly to the old behaviour (bbox center, min side).

    Falls back to the bounding box for degenerate rings.
    """
    xs, ys = path_data[:, 0], path_data[:, 1]
    left, right, top, bottom = np.min(xs), np.max(xs), np.min(ys), np.max(ys)
    bbox_fallback = ((left + right) / 2, (top + bottom) / 2,
                     min(right - left, bottom - top))
    try:
        polygon = Polygon(path_data)
        if not polygon.is_valid or polygon.is_empty:
            return bbox_fallback
        anchor = polylabel(polygon, tolerance=0.01 * max(right - left, bottom - top))
        clearance = polygon.exterior.distance(anchor)
        # The pole is non-unique on elongated shapes (any point along a
        # rectangle's center line ties) and polylabel picks an arbitrary
        # winner — keep the classic centered look whenever the bbox center
        # has essentially the same clearance.
        bbox_center = Point(bbox_fallback[0], bbox_fallback[1])
        if polygon.contains(bbox_center):
            bbox_clearance = polygon.exterior.distance(bbox_center)
            if bbox_clearance >= 0.95 * clearance:
                return bbox_fallback[0], bbox_fallback[1], 2 * bbox_clearance
        return anchor.x, anchor.y, 2 * clearance
    except Exception:
        return bbox_fallback
