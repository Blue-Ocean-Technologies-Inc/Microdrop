# -*- coding: utf-8 -*-

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import re
import xml.etree.ElementTree as ET

import numpy as np
from shapely.geometry import Polygon

from traits.api import (
    Bool,
    Dict,
    File,
    Float,
    HasTraits,
    Instance,
    List,
    Property,
    Str,
    Tuple,
    cached_property,
    observe,
)

from device_viewer.consts import ZONES_SVG_LAYER_LABEL
from device_viewer.utils.dmf_utils_helpers import (
    AlgorithmError,
    ElectrodeData,
    PolygonNeighborFinder,
    SVGProcessor,
    create_adjacency_dict,
)

from logger.logger_service import get_logger

logger = get_logger(__name__, "DEBUG")

# ------------------------- InkScape Consts ---------------------------------

float_pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
style_pattern = re.compile(r"fill:#[0-9a-fA-F]{6}")

# Define Namespaces
NS_SVG = "http://www.w3.org/2000/svg"
NS_INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"


class SvgUtil(HasTraits):
    filename = File(desc="Filename of SVG file with electrodes data")

    svg_error_paths = List(
        desc="Paths from file that could not be loaded into electrodes"
    )
    svg_exceptions_caught = List(desc="Exceptions caught on SVG loading")

    area_scale = Float(1.0)
    electrode_areas_scaled = Property(
        Dict(Str, Float),
        observe="[area_scale, electrode_areas.items]",
        desc="Area of electrodes scaled by area scale in mm2",
    )

    electrodes = Dict(
        Str,
        Instance(ElectrodeData),
        desc="keys are electrode id, values are electrode data "
        "providing path and channel data of the electrodes",
    )

    auto_found_connections = Bool(
        False, desc="whether connections were retrieved from file or auto generated"
    )
    zone_records = List(
        Dict, desc="Electrode zone regions stored in the SVG's Zones layer"
    )
    neighbours = Dict(
        Str,
        List(Str),
        desc="Map of electrode id to electrode ids of neighbouring electrodes",
    )
    connections = Dict(
        desc="Each item is a connections between two electrodes given bu its "
        "centroid coordinates"
    )

    polygons = Dict(
        Str, Instance(Polygon), desc="Polygon for each electrode keyed by its id"
    )
    electrode_centers = Dict(Str, Tuple(Float, Float), desc="Electrode centroid coords")
    electrode_areas = Dict(Str, Float, desc="Electrode areas")

    max_x = Float(desc="Max x coordinate of electrodes")
    max_y = Float(desc="Max y coordinate of electrodes")
    min_x = Float(desc="Min x coordinate of electrodes")
    min_y = Float(desc="Min y coordinate of electrodes")

    svg_processor = Instance(SVGProcessor)

    def traits_init(self):
        logger.debug("File changed")
        self.get_device_paths(self.filename)

    @observe("electrodes")
    def _electrodes_changed(self, event):
        self.min_x, self.min_y, self.max_x, self.max_y = (
            self.svg_processor.get_bounding_box()
        )
        logger.debug(f"Bounding box: {self.min_x, self.min_y, self.max_x, self.max_y}")

    @cached_property
    def _get_electrode_areas_scaled(self):
        if self.area_scale and self.electrode_areas:
            return {
                key: value * self.area_scale
                for key, value in self.electrode_areas.items()
            }
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

            elif ZONES_SVG_LAYER_LABEL.casefold() in [
                val.casefold() for val in child.attrib.values()
            ]:
                self.zone_records = self.extract_zone_records(child)

            elif child.tag == "{http://www.w3.org/2000/svg}metadata":
                scale = child.find("scale")
                if scale is not None:
                    self.area_scale = float(scale.text)
                    logger.info(
                        f"Pixel scale set to {self.area_scale} from SVG metadata."
                    )

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
                    self.neighbours = self.find_neighbours_all_from_connections(
                        connection_lines
                    )
                except AlgorithmError as e:
                    logger.error(e)
                    # publish this to have a popup inform user about this

            if len(self.neighbours.items()) == 0:
                logger.warning(
                    f"{self.filename} does not have extractable connection "
                    "elements. Will auto find the connections"
                )
                self.generate_connections_from_neighbouring_electrodes()

    def generate_connections_from_neighbouring_electrodes(self):
        self.neighbours = self.find_neighbours_all()
        self.auto_found_connections = True

    @staticmethod
    def extract_zone_records(group_element):
        """Region records from the Zones layer: one child element per region
        carrying data-zone-id / data-electrode-ids (space separated)."""
        records = []
        for element in group_element:
            electrode_ids = element.attrib.get("data-electrode-ids", "").split()
            zone_id = element.attrib.get("data-zone-id")
            if not zone_id or not electrode_ids:
                continue
            records.append(
                {
                    "id": element.attrib.get("id", ""),
                    "zone_id": zone_id,
                    "zone_name": element.attrib.get("data-zone-name", zone_id),
                    "zone_color": element.attrib.get("data-zone-color", ""),
                    "visible": element.attrib.get("data-visible", "true") != "false",
                    "electrode_ids": electrode_ids,
                }
            )
        return records

    def _write_zone_layer(self, root):
        """Replace the Zones layer with one built from ``zone_records``
        (dropped entirely when there are none)."""
        for child in list(root):
            if ZONES_SVG_LAYER_LABEL.casefold() in [
                val.casefold() for val in child.attrib.values()
            ]:
                root.remove(child)
        if not self.zone_records:
            return
        layer = ET.SubElement(
            root,
            f"{{{NS_SVG}}}g",
            {
                "id": "zones-layer",
                f"{{{NS_INKSCAPE}}}groupmode": "layer",
                f"{{{NS_INKSCAPE}}}label": ZONES_SVG_LAYER_LABEL,
            },
        )
        for record in self.zone_records:
            ET.SubElement(
                layer,
                f"{{{NS_SVG}}}g",
                {
                    "id": record["id"],
                    "data-zone-id": record["zone_id"],
                    "data-zone-name": record.get("zone_name", record["zone_id"]),
                    "data-zone-color": record.get("zone_color", ""),
                    "data-visible": "true" if record.get("visible", True) else "false",
                    "data-electrode-ids": " ".join(record["electrode_ids"]),
                },
            )

    def get_electrode_polygons(self) -> dict[str, Polygon]:
        polygons = {}
        errors_found = []
        exceptions = set()

        for k, v in list(self.electrodes.items()):
            try:
                coords = v.path.reshape(-1, 2)
                # Rings are repaired once, at the source (svg_to_electrodes
                # stores the as_valid_polygon exterior), so construction
                # here is plain — no per-call validity rescan.
                polygons[k] = Polygon(coords)
            except Exception as e:
                logger.error(f"Failed to create polygon for '{k}': {e}")
                errors_found.append(k)
                exceptions.add(e)
                del self.electrodes[k]

        if errors_found:
            self.svg_error_paths = errors_found
            self.svg_exceptions_caught = list(exceptions)

        return polygons

    def find_electrode_areas(self) -> dict[str, float]:
        """
        Find the areas of the electrodes
        """
        return {
            electrode_id: polygon.area
            for electrode_id, polygon in self.polygons.items()
        }

    def find_electrode_centroids(self) -> dict[str, tuple[float, float]]:
        return {
            electrode_id: polygon.centroid.coords[0]
            for electrode_id, polygon in self.polygons.items()
        }

    def find_neighbours_all(
        self, buffer_distance: float = None
    ) -> dict[str, list[str]]:

        if buffer_distance is None:
            buffer_distance = (
                sum(self.electrode_areas.values()) / len(self.electrodes.values()) / 100
            )

        neighbors = []
        for electrode_id_i, poly_i in self.polygons.items():
            poly_i = poly_i.buffer(buffer_distance).convex_hull

            for electrode_id_j, poly_j in self.polygons.items():
                poly_j = self.polygons[electrode_id_j]
                poly_j = poly_j.buffer(buffer_distance).convex_hull

                if electrode_id_i != electrode_id_j and (
                    poly_i.touches(poly_j) or poly_i.intersects(poly_j)
                ):
                    angle = np.arctan2(
                        poly_i.centroid.x - poly_j.centroid.x,
                        poly_i.centroid.y - poly_j.centroid.y,
                    )

                    angle = abs(np.degrees(angle))
                    if angle > 90:
                        angle = 180 - angle
                    # if the angle is between 30 and 70 degrees, the polygons
                    # are connected diagonally so the connections are excluded
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

    @observe("neighbours")
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
                    # Because of the arrow connections are not reverse-equivalent,
                    # so we need a connection for either direction
                    self.connections[(n, k)] = (
                        coord_n,
                        coord_k,
                    )

    @staticmethod
    def set_fill_black(obj: ET.Element) -> None:
        """
        Sets the fill of the svg paths to black in place
        :param obj: The svg element
        """
        for element in obj:
            try:
                element.attrib["style"] = re.sub(
                    style_pattern, r"fill:#000000", element.attrib["style"]
                )
            except KeyError:
                pass

    def get_connection_lines(self):
        """
        Returns paths for connection lines in the form (start_x, start_y, end_x, end_y).

        Can be used to get the connection lines between electrodes even if
        they were auto generated using the find_neighbours_all method.
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

        Reconstructs the svg xml tree before saving to new file, updating any
        data that could have changed:
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
                f"{{{NS_INKSCAPE}}}label": "Connections",
            }
            layer = ET.SubElement(root, f"{{{NS_SVG}}}g", layer_attribs)

            # Common style
            style = "stroke:#000000;stroke-width:0.128792"

            # Iterate through data and create <ns0:line> sub-elements
            # Store the coords in the original units user provided.
            # Undo the normalization to mm using the appropriate inverse
            # scaling function
            for index, (x1, y1, x2, y2) in enumerate(connection_lines):
                x1, y1, x2, y2 = (
                    str(self.svg_processor.unit_normalization_func_inverse(coord))
                    for coord in (x1, y1, x2, y2)
                )
                # save in DPI units in the file to match other svg files.
                line_attribs = {
                    "id": f"line{index}",
                    "style": style,
                    "x1": x1,
                    "x2": x2,
                    "y1": y1,
                    "y2": y2,
                }
                ET.SubElement(layer, f"{{{NS_SVG}}}line", line_attribs)

            # reset auto found connections flag in case user wants to do it again
            self.auto_found_connections = False

        ### Zones layer: always rewritten from the current regions ###
        self._write_zone_layer(root)

        ET.indent(root, space="  ")

        tree.write(file)
