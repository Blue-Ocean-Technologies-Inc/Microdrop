# -*- coding: utf-8 -*-
import re
import numpy as np
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon

from traits.api import HasTraits, Float, Dict, Str, Bool, File, observe, List, Instance, Tuple, Property, cached_property

from device_viewer.utils.dmf_utils_helpers import PolygonNeighborFinder, create_adjacency_dict, ElectrodeData, \
    SVGProcessor, AlgorithmError

from logger.logger_service import get_logger
logger = get_logger(__name__, "DEBUG")

# ------------------------- InkScape Consts ---------------------------------

float_pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
style_pattern = re.compile(r"fill:#[0-9a-fA-F]{6}")

# Define Namespaces
NS_SVG = "http://www.w3.org/2000/svg"
NS_INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"

class SvgUtil(HasTraits):
    filename = File(desc='Filename of SVG file with electrodes data')

    area_scale = Float(1.0)
    electrode_areas_scaled = Property(Dict(Str, Float), observe='[area_scale, electrode_areas.items]', desc='Area of electrodes scaled by area scale in mm2')

    electrodes = Dict(Str, Instance(ElectrodeData), desc="keys are electrode id, values are electrode data "
                                                         "providing path and channel data of the electrodes")

    auto_found_connections = Bool(False, desc='whether connections were retrieved from file or auto generated')
    neighbours = Dict(Str, List(Str), desc='Map of electrode id to electrode ids of neighbouring electrodes')
    connections = Dict(desc="Each item is a connections between two electrodes given bu its centroid coordinates")

    polygons = Dict(Str, Instance(Polygon), desc="Polygon for each electrode keyed by its id")
    electrode_centers = Dict(Str, Tuple(Float, Float), desc="Electrode centroid coords")
    electrode_areas = Dict(Str, Float, desc="Electrode areas")

    max_x = Float(desc='Max x coordinate of electrodes')
    max_y = Float(desc='Max y coordinate of electrodes')
    min_x = Float(desc='Min x coordinate of electrodes')
    min_y = Float(desc='Min y coordinate of electrodes')

    svg_processor = Instance(SVGProcessor)

    def traits_init(self):
        logger.debug("File changed")
        self.get_device_paths(self.filename)

    @observe('electrodes')
    def _electrodes_changed(self, event):
        self.min_x, self.min_y, self.max_x, self.max_y = self.svg_processor.get_bounding_box()
        logger.debug(f"Bounding box: {self.min_x, self.min_y, self.max_x, self.max_y}")

    @cached_property
    def _get_electrode_areas_scaled(self):
        if self.area_scale and self.electrode_areas:
            return {key: value * self.area_scale for key, value in self.electrode_areas.items()}
        elif self.electrode_areas:
            return self.electrode_areas
        else:
            return {}

    def get_device_paths(self, filename):

        self.svg_processor = svg_processor = SVGProcessor(filename=filename)

        ################################################
        ## Load Data from svg file
        ################################################

        connection_lines = None

        for child in svg_processor.root:
            if "device" in [val.casefold() for val in child.attrib.values()]:
                self.set_fill_black(child)
                self.electrodes = svg_processor.svg_to_electrodes(child)
                self.polygons = self.get_electrode_polygons()

            elif "connections" in [val.casefold() for val in child.attrib.values()]:
                connection_lines = svg_processor.extract_connections(child)

            elif child.tag == "{http://www.w3.org/2000/svg}metadata":
                scale = child.find("scale")
                if scale is not None:
                    self.area_scale = float(scale.text)
                    logger.info(f"Pixel scale set to {self.area_scale} from SVG metadata.")

        #########################################################################################
        ## Process svg data
        #########################################################################################
        if not self.polygons:
            logger.error("No polygons found in SVG file. Failed load attempt.")
            raise ValueError("No polygons found in SVG file. Failed load attempt.")

        if len(self.electrodes) > 0:
            self.electrode_centers = self.find_electrode_centroids()
            self.electrode_areas = self.find_electrode_areas()

            if connection_lines is not None:
                try:
                    self.neighbours = self.find_neighbours_all_from_connections(connection_lines)
                except AlgorithmError as e:
                    logger.error(e)
                    # publish this to have a popup inform user about this

            if len(self.neighbours.items()) == 0:
                logger.warning(f"{self.filename} does not have extractable connection elements. Will auto find the connections")
                self.generate_connections_from_neighbouring_electrodes()

    def generate_connections_from_neighbouring_electrodes(self):
        self.neighbours = self.find_neighbours_all()
        self.auto_found_connections = True

    def get_electrode_polygons(self) -> dict[str, Polygon]:
        """
        Get the polygons of the electrodes
        """
        return {k: Polygon(v.path.reshape(-1, 2)) for k, v in self.electrodes.items()}

    def find_electrode_areas(self) -> dict[str, float]:
        """
        Find the areas of the electrodes
        """
        return {electrode_id: polygon.area for electrode_id, polygon in self.polygons.items()}

    def find_electrode_centroids(self) -> dict[str, tuple[float, float]]:
        return {electrode_id: polygon.centroid.coords[0] for electrode_id, polygon in self.polygons.items()}

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

    @observe('neighbours')
    def neighbours_to_points(self, event):
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
                element.attrib['style'] = re.sub(style_pattern, r"fill:#000000", element.attrib['style'])
            except KeyError:
                pass

    def get_connection_lines(self):
        """
        Returns paths for connection lines in the form (start_x, start_y, end_x, end_y).

        Can be used to get the connection lines between electrodes even if they were auto generated using the
        find_neighbours_all method.
        """
        paths = []
        for key, value in self.neighbours.items():
            start_x, start_y = self.electrode_centers[key]
            for elec in value:
                end_x, end_y = self.electrode_centers[elec]
                if (end_x, end_y, start_x, start_y) not in paths:
                    paths.append((start_x, start_y, end_x, end_y))

        return paths

    def save_to_file(self, file, electrode_ids_channels_map: dict[str, int]):
        """
        Method to save current svg data to a new svg file.

        Reconstructs the svg xml tree before saving to new file, updating any data that could have changed:
        - Metadata
        - Connections
        - Electrode id to channel mapping.
        """

        # get original svg xml data
        tree = ET.parse(self.filename)
        root = tree.getroot()

        electrodes = None
        for child in root:
            if "device" in [val.casefold() for val in child.attrib.values()]:
                electrodes = child

            # Add metadata: e.g. area scale.
            elif child.tag == "{http://www.w3.org/2000/svg}metadata":
                scale_element = child.find("scale")
                if scale_element is None:
                    scale_element = ET.SubElement(child, "scale")

                scale_element.text = str(self.area_scale)

        if electrodes is None:
            logger.error("No electrodes found: Not saving to file...")
            return

        ### Add the channels for each electrode ###
        for electrode in list(electrodes):
            element_id = electrode.attrib.get("id")
            if element_id not in electrode_ids_channels_map:
                # Skip non-electrode elements (e.g. nested <g> groups like "g4")
                continue
            channel = electrode_ids_channels_map[element_id]
            if channel is not None:
                electrode.attrib["data-channels"] = str(channel)
            else:
                electrode.attrib.pop("data-channels", None)

        ### Add connections if autogenerated ###
        if self.auto_found_connections:
            logger.info("Writing auto found connections to save file")

            ### Remove pre-existing connections layer if it exists
            for child in root:
                if "connections" in [val.casefold() for val in child.attrib.values()]:
                    root.remove(child)

            connection_lines = self.get_connection_lines()

            # Create the Group < ns0: g >
            # Note: Attributes with namespaces also need the {namespace}key format
            layer_attribs = {
                "id": "layer2",
                f"{{{NS_INKSCAPE}}}groupmode": "layer",
                f"{{{NS_INKSCAPE}}}label": "Connections"
            }
            layer = ET.SubElement(root, f"{{{NS_SVG}}}g", layer_attribs)

            # Common style
            style = "stroke:#000000;stroke-width:0.128792"

            # Iterate through data and create <ns0:line> sub-elements
            # Store the coords in the original units user provided.
            # Undo the normalization to mm using the appropriate inverse scaling function
            for index, (x1, y1, x2, y2) in enumerate(connection_lines):
                x1, y1, x2, y2 = (str(self.svg_processor.unit_normalization_func_inverse(coord)) for coord in (x1, y1, x2, y2))
                # save in DPI units in the file to match other svg files.
                line_attribs = {
                    "id": f"line{index}",
                    "style": style,
                    "x1": x1,
                    "x2": x2,
                    "y1": y1,
                    "y2": y2
                }
                ET.SubElement(layer, f"{{{NS_SVG}}}line", line_attribs)

            # reset auto found connections flag in case user wants to do it again
            self.auto_found_connections = False


        ET.indent(root, space="  ")

        tree.write(file)