import numpy as np
from PySide6.QtGui import QColor, QPainterPath, QPen
from pyface.qt.QtCore import Qt

from .electrodes_view_base import ElectrodeConnectionItem
from .default_settings import default_colors
from device_viewer.models.route import Route
from shapely.geometry import LinearRing


def find_path_item(scene, connected_electrodes_keys):
    """Find a QGraphicsPathItem with the exact path sequence"""
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
