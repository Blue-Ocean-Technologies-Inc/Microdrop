import json
import timeit
import functools
from typing import Optional
import pandas as pd
import re
import numpy as np
import xml.etree.ElementTree as ET

from pathlib import Path
from typing import Union, TypedDict
from shapely.geometry import Polygon, Point

from traits.api import HasTraits, Float, Dict, Str

from device_viewer.utils.dmf_utils import create_adjacency_dict
from device_viewer.utils.dmf_utils_helpers import LinePolygonTreeQueryUtil

DPI = 96
INCH_TO_MM = 25.4

DOTS_TO_MM = INCH_TO_MM / DPI

def timeit_benchmark(number=100, repeat=3):
    """
    A decorator factory that benchmarks a function's execution time using timeit.

    Args:
        number (int): The number of times to execute the function per trial.
        repeat (int): The number of trials to run.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a callable for timeit that includes the function's arguments
            timed_func = lambda: func(*args, **kwargs)

            # --- Run the benchmark ---
            print(f"Running benchmark for '{func.__name__}'...")
            all_runs = timeit.repeat(
                stmt=timed_func,
                number=number,
                repeat=repeat
            )

            # --- Process and print results ---
            # The best time is the minimum, as it's least affected by system noise
            best_time = min(all_runs)
            avg_time_per_run = best_time / number

            print(f"--- Timing Results: {func.__name__} ---")
            print(f"  {repeat} trial(s), {number} run(s) per trial")
            print(f"  Best total time for {number} runs: {best_time:.6f} seconds")
            print(f"  Fastest average time per run: {avg_time_per_run:.6f} seconds")
            print("---")

            # Run the function one last time to get and return the actual result
            return func(*args, **kwargs)

        return wrapper

    return decorator



class ElectrodeDict(TypedDict):
    channel: int
    path: np.ndarray  # NDArray[Shape['*, 1, 1'], Float]


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
        self.polygons = None
        self.connections = {}
        self.neighbours_extracted = None
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

    def get_device_paths(self, filename, modify=False):
        tree = ET.parse(filename)
        root = tree.getroot()

        # ### MODIFICATION: Logic now populates self.neighbours first ###
        for child in root:
            if "Device" in child.attrib.values():
                self.set_fill_black(child)
                self.electrodes = self.svg_to_electrodes(child)
                self.polygons = self.get_electrode_polygons()
            elif "ROI" in child.attrib.values():
                self.roi = self.svg_to_paths(child)
            elif "Connections" in child.attrib.values():
                print("Found 'Connections' layer, extracting neighbours from SVG.")
                # The method now returns the neighbours dict directly
                self.neighbours_extracted = self.extract_connections(root, line_layer='Connections')
            elif child.tag == "{http://www.w3.org/2000/svg}metadata":
                # ... (metadata logic remains the same)
                scale = child.find("scale")
                if scale is not None:
                    self.area_scale = float(scale.text)
                    print(f"Pixel scale set to {self.area_scale} from SVG metadata.")

        if len(self.electrodes) > 0:
            self.find_electrode_centers()
            self.electrode_areas = self.find_electrode_areas()
            self.electrode_areas_scaled = {key: value * self.area_scale for key, value in self.electrode_areas.items()}

            # If neighbours weren't found in the SVG, use proximity search
            file = Path("neighbours_120pin.json")
            if self.filename.stem == "120_pin_array"  and file.exists():
                with open(file) as f:
                    self.neighbours = json.load(f)
            else:
                self.neighbours = self.find_neighbours_all()
            # self.neighbours2 = self.find_neighbours_all_2()
            #
            # if self.neighbours2 == self.neighbours:
            #     print('NEW METHOD MATCHES OLD METHOD FOR CONNECTION')

            if self.neighbours_extracted == self.neighbours:

                print('EXTRACTION METHOD WORKED')

            else:
                failed_keys = []
                for keys in self.neighbours:
                    if sorted(self.neighbours[keys]) == sorted(self.neighbours_extracted[keys]):
                        # print(f'EXTRACTION METHOD WORKED for {keys}')
                        pass
                    else:
                        print(f'EXTRACTION FAILED FOR {keys}')
                        failed_keys.append(keys)


                if len(failed_keys) > 0:
                    out_msg = f"EXTRACTION FAILED FOR {failed_keys}"
                else:
                    out_msg = f"EXTRACTION SUCCESS"

                print("*" * 1000)
                print(out_msg)
                print("*" * 1000)

            # ALWAYS generate connection points from the final neighbours dictionary
            self.neighbours_to_points()

        if modify:
            tree.write(filename)


    def get_electrode_center(self, electrode: str) -> np.ndarray:
        """
        Get the center of an electrode
        """
        return np.mean(self.electrodes[electrode]['path'], axis=0)

    # @timeit_benchmark(number=1, repeat=1)
    def find_electrode_centers(self):
        self.electrode_centers = {}

        for id, _ in self.electrodes.items():
            self.electrode_centers[id] = self.get_electrode_center(id)

    # @timeit_benchmark(number=1, repeat=1)
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

    # @timeit_benchmark(number=1, repeat=1)
    def find_electrode_areas(self) -> dict[str, float]:
        """
        Find the areas of the electrodes
        """
        return {electrode_id: polygon.area for electrode_id, polygon in self.get_electrode_polygons().items()}

    # @timeit_benchmark(number=1, repeat=1)
    def find_neighbours_all(self, threshold: [float, None] = None) -> dict[str, list[str]]:
        """
        Find the neighbours of all paths
        """
        # if threshold is None then try to calculate it by finding the closest two electrodes centers
        if threshold is None:
            # Dilate the polygons
            polygons = self.polygons
            distances = sorted([v1.buffer(-0.1).distance(v2.buffer(-0.1)) for k1, v1 in polygons.items()
                                for k2, v2 in polygons.items() if k1 != k2])
            average_distance = np.mean(distances[:len(self.electrodes)])

            # Dilate the polygons by the average distance
            polygons = {k: v.buffer(average_distance) for k, v in polygons.items()}

            # Find the intersecting polygons
            neighbours = {}
            for k1, v1 in polygons.items():
                for k2, v2 in polygons.items():
                    if k1 != k2:
                        intersection = v1.intersection(v2)
                        if intersection.area >= average_distance:
                            neighbours.setdefault(k1, []).append(k2)
        else:
            neighbours = {}
            for k, v in self.electrodes.items():
                neighbours[k] = self.find_neighbours(v['path'], threshold)
                # remove self from neighbours
                neighbours[k].remove(k)
        return neighbours

    # @timeit_benchmark(number=1, repeat=1)
    def find_neighbours_all_2(self, buffer_distance: float = None) -> dict[str, list[str]]:

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

    # @timeit_benchmark(number=1, repeat=1)
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
                    self.connections[(n, k)] = (coord_n,
                                                coord_k)  # Because of the arrow connections are not reverse-equivalent, so we need a connection for either direction

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

            paths.append(np.array(moves).reshape((-1, 1, 2)) * DOTS_TO_MM)

        self.max_x = max([p[..., 0].max() for p in paths])
        self.max_y = max([p[..., 1].max() for p in paths])
        self.min_x = min([p[..., 0].min() for p in paths])
        self.min_y = min([p[..., 1].min() for p in paths])

        return paths

    # @timeit_benchmark(number=1, repeat=1)
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
            electrodes[element.attrib['id']]['path'] *= DOTS_TO_MM

        self.max_x = max([e['path'][..., 0].max() for e in electrodes.values()])
        self.max_y = max([e['path'][..., 1].max() for e in electrodes.values()])
        self.min_x = min([e['path'][..., 0].min() for e in electrodes.values()])
        self.min_y = min([e['path'][..., 1].min() for e in electrodes.values()])

        return electrodes

    def find_shape(self, x: float, y: float, polygons: dict[str, Polygon] = None) -> Optional[str]:
        """
        Finds the electrode ID of the shape containing the given coordinate.

        Args:
            x (float): The x-coordinate.
            y (float): The y-coordinate.

        Returns:
            Optional[str]: The ID of the electrode, or None if no shape is found.
        """
        if not polygons:
            polygons = self.get_electrode_polygons()

        for electrode_id, polygon in polygons.items():
            if Point(x, y).intersects(polygon):
                print(f"Found electrode ID: {electrode_id}")
                return electrode_id

        return None

    # @timeit_benchmark(number=1, repeat=1)
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

        if buffer_distance is None:
            buffer_distance = sum(self.electrode_areas.values()) / len(self.electrodes.values()) / 100

        tree_query = LinePolygonTreeQueryUtil(
            polygons=_polygons,
            polygon_names=_polygons_names,
            lines=_lines,
            line_names=_line_names,
        )

        return tree_query.line_polygon_mapping


try:
    from importlib.resources import as_file, files
except ImportError:
    from importlib_resources import as_file, files

device_repo = files('device_viewer.resources.devices')

device_120_pin_path = device_repo / "120_pin_array.svg"
device_90_pin_path = device_repo / "90_pin_array.svg"

# @timeit_benchmark(number=1, repeat=1)
def main():
    device_90_pin_model = SvgUtil(device_90_pin_path)
    device_120_pin_model = SvgUtil(device_120_pin_path)

main()