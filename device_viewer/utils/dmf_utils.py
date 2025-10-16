# -*- coding: utf-8 -*-
import re
import numpy as np
import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union, TypedDict, Optional
from shapely.geometry import Polygon

from traits.api import HasTraits, Float, Dict, Str

from device_viewer.utils.dmf_utils_helpers import LinePolygonTreeQueryUtil, create_adjacency_dict

from microdrop_utils._logger import get_logger
logger = get_logger(__name__)

DPI=96
INCH_TO_MM = 25.4
DOTS_TO_MM = INCH_TO_MM / DPI


class ElectrodeDict(TypedDict):
    channel: int
    path: np.ndarray # NDArray[Shape['*, 1, 1'], Float]


class SvgUtil(HasTraits):
    float_pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    path_commands = re.compile(r"(?P<move_command>[ML])\s+(?P<x>{0}),\s*(?P<y>{0})\s*|"
                               r"(?P<x_command>[H])\s+(?P<hx>{0})\s*|"
                               r"(?P<y_command>[V])\s+(?P<vy>{0})\s*|"
                               r"(?P<command>[Z])"
                               .format(float_pattern))
    style_pattern = re.compile(r"fill:#[0-9a-fA-F]{6}")

    area_scale = Float
    electrode_areas_scaled = Dict(Str, Float)

    def __init__(self, filename: Union[str, Path] = None, **traits):
        super().__init__(**traits)
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
        self.roi: list[np.ndarray] = []
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
        tree = ET.parse(filename)
        root = tree.getroot()

        for child in root:
            if "Device" in child.attrib.values():
                self.set_fill_black(child)
                self.electrodes = self.svg_to_electrodes(child)
                self.polygons = self.get_electrode_polygons()
            elif "ROI" in child.attrib.values():
                self.roi = self.svg_to_paths(child)
            elif "Connections" in child.attrib.values():
                self.neighbours = self.extract_connections(root, line_layer='Connections')

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

            self.neighbours_to_points()

    def get_electrode_center(self, electrode: str) -> np.ndarray:
        """
        Get the center of an electrode
        """
        return np.mean(self.electrodes[electrode]['path'], axis=0)

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

    def extract_connections(self, root: ET.Element, line_layer: str = 'Connections',
                            line_xpath: Optional[str] = None, path_xpath: Optional[str] = None,
                            namespaces: Optional[dict] = None, buffer_distance: float = None) -> dict:
        """
        Parses <line> and <path> elements from a layer to find connections
        (neighbours) between electrodes. Returns a dictionary mapping each
        electrode ID to a list of its neighbours.
        """
        if namespaces is None:
            namespaces = {'svg': 'http://www.w3.org/2000/svg',
                          'inkscape': 'http://www.inkscape.org/namespaces/inkscape'}

        frames = []
        # List to hold records of form: `[<id>, <x1>, <y1>, <x2>, <y2>]`.
        coords_columns = ['x1', 'y1', 'x2', 'y2']

        if line_xpath is None:
            # Define a query to look for `svg:line` elements in the top level of layer of
            # SVG specified to contain connections.
            line_xpath = f".//svg:g[@inkscape:label='{line_layer}']/svg:line"

        for line_i in root.findall(line_xpath, namespaces=namespaces):
            line_i_dict = dict(line_i.items())
            values = [line_i_dict.get('id')] + [float(line_i_dict[k]) for k in coords_columns]
            frames.append(values)

        cre_path_ends = re.compile(r'^\s*M\s*(?P<start_x>{0}),\s*(?P<start_y>{0})'
                                   r'.*((L\s*(?P<end_x>{0}),\s*(?P<end_y>{0}))|'
                                   r'(V\s*(?P<end_vy>{0}))|'
                                   r'(H\s*(?P<end_hx>{0})))\D*$'.format(self.float_pattern))
        if path_xpath is None:
            path_xpath = f".//svg:g[@inkscape:label='{line_layer}']/svg:path"

        for path_i in root.findall(path_xpath, namespaces=namespaces):
            path_i_dict = dict(path_i.items())
            match_i = cre_path_ends.match(path_i_dict.get('d', ''))
            # Connection `svg:path` matched required format.  Extract start and
            # end coordinates.
            if match_i:
                match_dict_i = match_i.groupdict()
                if match_dict_i.get('end_vy'):
                    match_dict_i['end_x'] = match_dict_i['start_x']
                    match_dict_i['end_y'] = match_dict_i['end_vy']
                if match_dict_i.get('end_hx'):
                    match_dict_i['end_x'] = match_dict_i['end_hx']
                    match_dict_i['end_y'] = match_dict_i['start_y']
                frames.append([path_i_dict.get('id')] + list(map(float,
                                                                 (match_dict_i['start_x'], match_dict_i['start_y'],
                                                                  match_dict_i['end_x'], match_dict_i['end_y']))))

        if not frames:
            return {}

        df_connection_lines = pd.DataFrame(frames, columns=['id'] + coords_columns)

        _polygons_names = list(self.polygons.keys())
        _polygons = list(self.polygons.values())

        _lines = (df_connection_lines.drop("id", axis=1) * DOTS_TO_MM).values
        _line_names = df_connection_lines["id"].values

        tree_query = LinePolygonTreeQueryUtil(
            polygons=_polygons,
            polygon_names=_polygons_names,
            lines=_lines,
            line_names=_line_names,
        )

        return tree_query.polygon_neighbours

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

    def svg_to_paths(self, obj) -> list[np.ndarray]:
        """
        Converts the svg file to paths
        """

        paths = []
        for path in obj:
            path = path.attrib["d"]
            moves = []
            for match in self.path_commands.findall(path):
                if ("M" in match) or ("L" in match):
                    moves.append((float(match[1]), float(match[2])))
                elif "H" in match:
                    moves.append((float(match[4]), moves[-1][1]))
                elif "V" in match:
                    moves.append((moves[-1][0], (float(match[6]))))
                elif "Z" in match:
                    pass

            paths.append(np.array(moves).reshape((-1, 1, 2)) * INCH_TO_MM / DPI)

        self.max_x = max([p[..., 0].max() for p in paths])
        self.max_y = max([p[..., 1].max() for p in paths])
        self.min_x = min([p[..., 0].min() for p in paths])
        self.min_y = min([p[..., 1].min() for p in paths])

        return paths

    def svg_to_electrodes(self, obj: ET.Element) -> dict[str, ElectrodeDict]:
        """
        Converts the svg file to paths
        """

        electrodes: dict[str, ElectrodeDict] = {}
        try:
            pattern = r"translate\((?P<x>-?\d+\.\d+),(?P<y>-?\d+\.\d+)\)"
            match = re.match(pattern, obj.attrib['transform'])
            x = float(match.group('x'))
            y = float(match.group('y'))
            transform = np.array([x, y])
        except KeyError:
            transform = np.array([0, 0])

        for element in list(obj):
            path = element.attrib["d"]
            moves = []
            for match in self.path_commands.findall(path):
                if ("M" in match) or ("L" in match):
                    moves.append((float(match[1]), float(match[2])))
                elif "H" in match:
                    moves.append((float(match[4]), moves[-1][1]))
                elif "V" in match:
                    moves.append((moves[-1][0], (float(match[6]))))
                elif "Z" in match:
                    pass

            try:
                electrodes[element.attrib['id']] = {'channel': int(element.attrib['data-channels']),
                                                    'path': (np.array(moves) + transform).reshape((-1, 2))}
            except KeyError:
                electrodes[element.attrib['id']] = {'channel': None,
                                                    'path': (np.array(moves) + transform).reshape((-1, 2))}

            # scale to mm
            electrodes[element.attrib['id']]['path'] *= INCH_TO_MM / DPI

        self.max_x = max([e['path'][..., 0].max() for e in electrodes.values()])
        self.max_y = max([e['path'][..., 1].max() for e in electrodes.values()])
        self.min_x = min([e['path'][..., 0].min() for e in electrodes.values()])
        self.min_y = min([e['path'][..., 1].min() for e in electrodes.values()])

        return electrodes