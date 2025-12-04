# -*- coding: utf-8 -*-
import re
import numpy as np
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union
from shapely.geometry import Polygon

from traits.api import HasTraits, Float, Dict, Str

from device_viewer.utils.dmf_utils_helpers import PolygonNeighborFinder, create_adjacency_dict, ElectrodeDict, \
    SVGProcessor

from logger.logger_service import get_logger
logger = get_logger(__name__)

DPI=96
INCH_TO_MM = 25.4
DOTS_TO_MM = INCH_TO_MM / DPI


class SvgUtil(HasTraits):
    float_pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    style_pattern = re.compile(r"fill:#[0-9a-fA-F]{6}")

    area_scale = Float
    electrode_areas_scaled = Dict(Str, Float)

    def __init__(self, filename: Union[str, Path] = None, **traits):
        super().__init__(**traits)
        self.auto_found_connections = False  # whether connections were retrieved from file or auto generated.
        self._filename = filename
        self.max_x = None
        self.max_y = None
        self.min_x = None
        self.min_y = None
        self.multi_x = None
        self.multi_y = None
        self.x_shift = None
        self.y_shift = None
        self.neighbours: dict[str, list[str]] = {}
        self.electrodes: dict[str, ElectrodeDict] = {}
        self.polygons = {}
        self.connections = {}
        self.electrode_centers = {}
        self.electrode_areas = {}
        self.area_scale = 1.0

        if self._filename:
            self.get_device_paths(self._filename)

    @property
    def filename(self) -> Union[str, Path]:
        return self._filename

    @filename.setter
    def filename(self, filename: Union[str, Path]):
        self._filename = filename
        self.get_device_paths(self._filename)

    def get_device_paths(self, filename):

        svg_processor = SVGProcessor(filename=filename)

        for child in svg_processor.root:
            if "Device" in child.attrib.values():
                self.set_fill_black(child)
                self.electrodes = svg_processor.svg_to_electrodes(child)
                self.min_x, self.min_y, self.max_x, self.max_y = svg_processor.get_bounding_box()

                self.polygons = self.get_electrode_polygons()

            elif "Connections" in child.attrib.values():
                connection_lines = svg_processor.extract_connections(child)
                if connection_lines is not None:
                    self.neighbours = self.find_neighbours_all_from_connections(connection_lines)
                else:
                    logger.warning(f"{self.filename} does not have extractable connection elements. Will auto find the connections")

            elif child.tag == "{http://www.w3.org/2000/svg}metadata":
                scale = child.find("scale")
                if scale is not None:
                    self.area_scale = float(scale.text)
                    print(f"Pixel scale set to {self.area_scale} from SVG metadata.")

        if len(self.electrodes) > 0:
            self.find_electrode_centers()
            self.electrode_areas = self.find_electrode_areas()
            self.electrode_areas_scaled = {key: value * self.area_scale for key, value in self.electrode_areas.items()}

            if len(self.neighbours.items()) == 0:
                self.neighbours = self.find_neighbours_all()
                self.auto_found_connections = True

            self.neighbours_to_points()

    def get_electrode_center(self, electrode: str) -> np.ndarray:
        """
        Get the center of an electrode
        """
        # exclude last element in path that indicates path is closed.
        return np.mean(self.electrodes[electrode]['path'][:-1], axis=0)

    def find_electrode_centers(self):
        self.electrode_centers = {}

        for id, _ in self.electrodes.items():
            self.electrode_centers[id] = self.get_electrode_center(id)

    def find_neighbours(self, path: np.ndarray, threshold: float = 10) -> list[str]:
        """
        Find the neighbours of a path
        """
        neighbours = []
        for k, v in self.electrodes.items():
            if np.linalg.norm(path[0, 0] - v['path'][0, 0]) < threshold:
                neighbours.append(k)
        return neighbours

    def get_electrode_polygons(self) -> dict[str, Polygon]:
        """
        Get the polygons of the electrodes
        """
        return {k: Polygon(v['path'].reshape(-1, 2)) for k, v in self.electrodes.items()}
    
    def find_electrode_areas(self) -> dict[str, float]:
        """
        Find the areas of the electrodes
        """
        return {electrode_id: polygon.area for electrode_id, polygon in self.get_electrode_polygons().items()}

    def find_neighbours_all(self, buffer_distance: float = None) -> dict[str, list[str]]:

        if buffer_distance is None:
            buffer_distance = sum(self.electrode_areas.values()) / len(self.electrodes.values()) / 100

        neighbors = []
        for electrode_id_i, poly_i in self.polygons.items():
            poly_i = poly_i.buffer(buffer_distance).convex_hull

            for electrode_id_j, poly_j in self.polygons.items():
                poly_j = self.polygons[electrode_id_j]
                poly_j = poly_j.buffer(buffer_distance).convex_hull

                if electrode_id_i != electrode_id_j and (poly_i.touches(poly_j) or poly_i.intersects(poly_j)):
                    angle = np.arctan2(poly_i.centroid.x - poly_j.centroid.x,
                                       poly_i.centroid.y - poly_j.centroid.y)

                    angle = abs(np.degrees(angle))
                    if angle > 90:
                        angle = 180 - angle
                    # if the angle is between 30 and 70 degrees, the polygons are connected diagonally
                    # so the connections are excluded
                    if angle < 30 or angle > 70:
                        neighbors.append((electrode_id_i, electrode_id_j))

        return create_adjacency_dict(neighbors)

    def find_neighbours_all_from_connections(self, connection_lines) -> dict:
        """
        Parses <line> and <path> elements from a layer to find connections
        (neighbours) between electrodes. Returns a dictionary mapping each
        electrode ID to a list of its neighbours.
        """


        _polygons_names = list(self.polygons.keys())
        _polygons = list(self.polygons.values())

        tree_query = PolygonNeighborFinder(
            polygons=_polygons,
            polygon_names=_polygons_names,
            lines=connection_lines,
        )

        return tree_query.get_polygon_neighbours()

    def neighbours_to_points(self):
        # Dictionary to store electrode connections
        self.connections = {}

        for k, v in self.neighbours.items():
            for n in v:
                if (n, k) not in self.connections and (k, n) not in self.connections:
                    coord_k = self.electrode_centers[k]
                    coord_n = self.electrode_centers[n]

                    # Store electrode pair (sorted for uniqueness) and their coordinates
                    self.connections[(k, n)] = (coord_k, coord_n)
                    self.connections[(n, k)] = (coord_n, coord_k) # Because of the arrow connections are not reverse-equivalent, so we need a connection for either direction

    @staticmethod
    def set_fill_black(obj: ET.Element) -> None:
        """
        Sets the fill of the svg paths to black in place
        :param obj: The svg element
        """
        for element in obj:
            try:
                element.attrib['style'] = re.sub(SvgUtil.style_pattern, r"fill:#000000", element.attrib['style'])
            except KeyError:
                pass