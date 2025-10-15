from pathlib import Path
import ezdxf

import numpy as np
import matplotlib.pyplot as plt

from ezdxf import units
from ezdxf.math import Matrix44
from ezdxf.upright import upright_all
from ezdxf.path import render_lwpolylines
from ezdxf.fonts.font_face import FontFace
from ezdxf.addons.text2path import make_paths_from_str

from shapely.ops import unary_union
from shapely.geometry.polygon import orient
from shapely.affinity import scale, translate
from shapely.geometry import LineString, Polygon, MultiPolygon, Point

from offset_dxf import multi_offset_shape

SCRIPT_DIR = Path(__file__).resolve().parent
path = SCRIPT_DIR.parent / "120-pin_v5 copy.dxf"


# voids_path = SCRIPT_DIR.parent / "voids3.dxf"


def dxf_entity_to_points(entity_, circle_points=100):
    points = None
    if entity_.dxftype() == "LINE":
        points = np.array([entity_.dxf.start, entity_.dxf.end])
    elif entity_.dxftype() == "LWPOLYLINE":
        points = np.array(entity_.get_points())
        if len(points) > 2:
            points = np.vstack([points, points[0]])
    elif entity_.dxftype() == "ARC":
        start_angle = entity_.dxf.start_angle
        end_angle = entity_.dxf.end_angle
        radius = entity_.dxf.radius
        center = entity_.dxf.center
        points = np.array([center + radius * np.array([np.cos(start_angle), np.sin(start_angle)]),
                           center + radius * np.array([np.cos(end_angle), np.sin(end_angle)]),
                           center + radius * np.array([np.cos(start_angle + (end_angle - start_angle) / 2),
                                                       np.sin(start_angle + (end_angle - start_angle) / 2)])])
    elif entity_.dxftype() == "CIRCLE":
        center = entity_.dxf.center
        radius = entity_.dxf.radius
        points = np.array([center + radius * np.array([np.cos(angle), np.sin(angle)])
                           for angle in np.linspace(0, 2 * np.pi, circle_points)])

    return points[..., :2]


def shape_to_polyline(shape_, min_gap=0.01) -> np.array:
    """
    Convert a shape to a polyline
    will also look for the largest distance between two points and break the shape at that point with a gap
    :param shape_: the shape to convert
    :param min_gap: the minimum gap between two points
    :return: polyline
    """
    if isinstance(shape_, LineString):
        coords = shape_.coords
    elif isinstance(shape_, Polygon):
        coords = shape_.exterior.coords
    else:
        return []
    if len(coords):
        coords = np.array(list(coords))
        # find the largest distance between two points
        distances = np.linalg.norm(coords - np.roll(coords, 1, axis=0), axis=1)
        max_distance = np.max(distances)
        if max_distance > min_gap:
            # find the index of the largest distance
            index = np.argmax(distances)
            coords = np.insert(coords, index, coords[index] + (coords[index - 1] - coords[index]) / 2, axis=0)

    return coords


def cut_wires(shape_, wire_thickness=0.08):
    shape_ = shape_.buffer(-wire_thickness, cap_style="square", join_style="mitre")
    if isinstance(shape_, Polygon):
        return shape_.buffer(wire_thickness, cap_style="square", join_style="mitre")
    elif isinstance(shape_, MultiPolygon):
        return [geom.buffer(wire_thickness, cap_style="square", join_style="mitre") for geom in shape_.geoms]


def orient_shape(shape_, line_):
    shape_ = orient(shape_)
    perimeter_ = np.array(shape_.exterior.coords)

    def f(x):
        return Point(x).distance(line_)

    # rotate the perimeter so that the first vertex is the closest to the line
    first_vertex = np.array(list(map(f, perimeter_))).argmin()
    perimeter_ = np.roll(perimeter_, -first_vertex, axis=0)
    # add another point between the first and last point in the y middle of the two
    x1, y1 = perimeter_[0]
    x2, y2 = perimeter_[1]
    if round(x1, 3) != round(x2, 3):
        x2, y2 = perimeter_[-1]
        y = min(y1, y2) + abs(y1 - y2) / 2
        perimeter_ = np.insert(perimeter_, 0, [x1, y - 0.01], axis=0)
        perimeter_ = np.insert(perimeter_, 0, [x1, y + 0.01], axis=0)
        # perimeter_ = np.roll(perimeter_, 1, axis=0)
    else:
        y = min(y1, y2) + abs(y1 - y2) / 2
        perimeter_ = np.insert(perimeter_, 1, [x1, y - 0.01], axis=0)
        perimeter_ = np.insert(perimeter_, 1, [x1, y + 0.01], axis=0)
        perimeter_ = np.roll(perimeter_, -1, axis=0)

    return orient(Polygon(perimeter_))


def add_shapes_to_dxf(shapes_, msp, layer, close=True):
    counter = 0
    for shape in shapes_:
        if not close:
            msp.add_lwpolyline(shape, dxfattribs={'layer': layer})
            counter += 1
            continue

        if shape.is_empty:
            continue
        polyline = shape_to_polyline(shape)
        if len(polyline):
            msp.add_lwpolyline(polyline, dxfattribs={'layer': layer})
            counter += 1
    return counter


def open_path(shape_, left=True, pad=False, offset=0.05):
    coordinates = list(shape_.exterior.coords)[1:]
    x1, y1 = coordinates[-2]
    x2, y2 = coordinates[1]

    if pad:
        min_y = shape_.bounds[1]
        max_y = shape_.bounds[3]

        if y1 - offset < min_y:
            coordinates[0] = [x2, y1 + offset]
        else:
            coordinates[0] = [x2, y1 - offset]

        if y2 - offset < min_y:
            coordinates[-1] = [x1, y2 + offset]
        else:
            coordinates[-1] = [x1, y2 - offset]

        return coordinates

    if left:
        coordinates[0] = [x2, y1 - offset]
        coordinates[-1] = [x1, y2 + offset]
        return coordinates
    else:
        coordinates[0] = [x2, y1 + offset]
        coordinates[-1] = [x1, y2 - offset]
        return coordinates


def dxf_post_process(path_, wire_thickness=0.1, beam_width=0.03):
    # Resolve input path relative to this file's directory
    path_obj = Path(path_)
    if not path_obj.is_absolute():
        path_obj = (SCRIPT_DIR / path_obj).resolve()

    print(f'Loaded file: {path_obj}')
    filename = path_obj.stem

    doc = ezdxf.readfile(str(path_obj))
    msp = doc.modelspace()
    upright_all(msp)
    shapes = []
    for entity in msp:
        shape = dxf_entity_to_points(entity)
        if len(shape) > 3:
            shapes.append(Polygon(shape))
        else:
            pass
            # shapes.append(LineString(shape))

    print(f'Number of shapes: {len(shapes)}')

    # sort the original shapes by area
    shapes.sort(key=lambda x: x.area, reverse=True)

    # Draw two lines one on either side of the largest shape
    # find the largest shape
    largest_shape = shapes[0]
    line_left = LineString([(largest_shape.bounds[0], largest_shape.bounds[1]),
                            (largest_shape.bounds[0], largest_shape.bounds[3])])
    line_right = LineString([(largest_shape.bounds[2], largest_shape.bounds[1]),
                             (largest_shape.bounds[2], largest_shape.bounds[3])])

    # Create voids into the largest shape
    void_poly = MultiPolygon(shapes[1:])
    voids = largest_shape.difference(void_poly, grid_size=.0001)
    if isinstance(voids, MultiPolygon):
        voids = list(voids.geoms)

    outside = unary_union(void_poly)
    if isinstance(outside, MultiPolygon):
        outside = outside.geoms[0]

    # offset inwards each shape by half the beam width
    offset_shapes_1 = [orient(item) for shape in voids
                       for item in multi_offset_shape(shape, iterations=1, beam_width=beam_width / 2)]
    # add the second largest shape to the offset shapes, offset outwards
    offset_shapes_1.extend(multi_offset_shape(orient(outside), beam_width=beam_width / 2, iterations=1, direction=1))
    offset_shapes_1[-1] = orient(offset_shapes_1[-1])

    # offset each shape by the beam width
    offset_shapes_2 = [orient(item) for shape in voids for item in
                       multi_offset_shape(shape, iterations=1, beam_width=beam_width)]
    outside_off = multi_offset_shape(orient(outside), beam_width=beam_width, iterations=1, direction=1)[0]

    # add the outside to the voids
    voids.append(orient(outside))

    # sort the offset shapes by area
    offset_shapes_2 = sorted(offset_shapes_2, key=lambda x: x.area, reverse=True)
    exterior = offset_shapes_2.pop(0)
    # find the y center of the exterior shape
    center_ext = exterior.centroid.y
    exterior = np.array(exterior.exterior.coords)
    interior = np.array(outside_off.exterior.coords)
    # cut the shape at the y value of the center
    exterior_top = exterior[exterior[:, 1] > center_ext]
    exterior_bot = exterior[exterior[:, 1] < center_ext]
    # remove duplicates
    exterior_top = np.unique(exterior_top, axis=0)
    exterior_bot = np.unique(exterior_bot, axis=0)

    # find the left most point of the interior shape and roll it to the start
    idx_int = np.argmin(interior[:, 0]) + 1
    interior = np.roll(interior, -idx_int, axis=0)

    # cut the interior shape at the y value of the center
    interior_top = interior[interior[:, 1] > center_ext]
    interior_bot = interior[interior[:, 1] < center_ext]

    # find the left and right most point of the interior shapes
    idx_top = np.argmin(interior_top[:, 0])
    left_top_int = interior_top[idx_top]
    right_top_int = interior_top[np.argmax(interior_top[:, 0])]
    idx_bot = np.argmin(interior_bot[:, 0])
    left_bot_int = interior_bot[idx_bot]
    right_bot_int = interior_bot[np.argmax(interior_bot[:, 0])]

    top_shape = np.vstack([exterior_top[::-1], [exterior_top[0][0], center_ext],
                           [left_top_int[0], center_ext], interior_top, [right_top_int[0], center_ext],
                           [exterior_top[-1][0], center_ext]])

    bot_shape = np.vstack([exterior_bot[::-1], [exterior_bot[0][0], center_ext],
                           [left_bot_int[0], center_ext], interior_bot[::-1], [right_bot_int[0], center_ext],
                           [exterior_bot[-1][0], center_ext]])

    top_shape = Polygon(top_shape)
    bot_shape = Polygon(bot_shape)
    offset_shapes_2.append(orient(top_shape))
    offset_shapes_2.append(orient(bot_shape))

    # categorize the shapes into left or right based on their Euclidean distance to the lines
    left_shapes = []
    right_shapes = []
    for shape in shapes[1:]:
        if shape.is_empty:
            continue
        if shape.distance(line_left) < shape.distance(line_right):
            left_shapes.append(shape)
        else:
            right_shapes.append(shape)

    # starting from the bottom left corner of the largest shape create points
    # with spacing 2.54mm, 6.35 mm from the bottom and 1.317 mm from the left
    # in a 15 x 4 array
    bot_x = largest_shape.bounds[0] + 1.317 + 2.54 / 2
    bot_y = largest_shape.bounds[1] + 6.35 + 2.54 / 2
    channels = []
    for i in range(4):
        for j in range(15):
            x = bot_x + i * 2.54
            y = bot_y + j * 2.54
            channel = 3 * (j + 1) - i + j
            channels.append((Point(x, y), channel))
    # Do the opposite for the right side
    bot_x = largest_shape.bounds[2] - 1.317 - 2.54 / 2
    for i in range(4):
        for j in range(15):
            x = bot_x - i * 2.54
            y = bot_y + j * 2.54
            channel = 116 + i - 4 * j
            channels.append((Point(x, y), channel))

    structures = {"pads": [],
                  "assignments": [],
                  "electrode_groups": {"electrodes_simple": [], "pads": [],
                                       "electrodes": [], "original": [], "channel": [],
                                       "open": []}}
    for shape in left_shapes:
        cut = cut_wires(shape, wire_thickness)
        if isinstance(cut, Polygon):
            pad_structure = orient_shape(cut, line_left)
            structures["pads"].append(pad_structure)
        elif isinstance(cut, list):
            pad = cut[0]
            for center, channel in channels:
                if pad.contains(center):
                    structures["electrode_groups"]["channel"].append(channel)
                    break
            structures["electrode_groups"]["pads"].append(pad)
            structures["electrode_groups"]["electrodes_simple"].append(cut[-1])
            mopa_structure = orient_shape(shape, line_left)
            structures["electrode_groups"]["original"].append(mopa_structure)
            structures["electrode_groups"]["open"].append(open_path(mopa_structure, left=True))
            wire = shape.difference(cut[-1])
            if isinstance(wire, MultiPolygon):
                # find the left most polygon
                wire = sorted(wire.geoms, key=lambda x: x.bounds[0])[0]
            electrode = shape.difference(wire)
            electrode = electrode.buffer(-beam_width / 2, cap_style="square", join_style="mitre")
            structures["electrode_groups"]["electrodes"].append(orient(electrode))

    for shape in right_shapes:
        cut = cut_wires(shape, wire_thickness)
        if isinstance(cut, Polygon):
            pad_structure = orient_shape(cut, line_right)
            structures["pads"].append(pad_structure)
        elif isinstance(cut, list):
            pad = cut[-1]
            for center, channel in channels:
                if pad.contains(center):
                    structures["electrode_groups"]["channel"].append(channel)
                    break
            structures["electrode_groups"]["pads"].append(pad)
            structures["electrode_groups"]["electrodes_simple"].append(cut[0])
            mopa_structure = orient_shape(shape, line_right)
            structures["electrode_groups"]["original"].append(mopa_structure)
            structures["electrode_groups"]["open"].append(open_path(mopa_structure, left=False))
            wire = shape.difference(cut[0])
            if isinstance(wire, MultiPolygon):
                # find the right most polygon
                wire = sorted(wire.geoms, key=lambda x: x.bounds[2], reverse=True)[0]
            electrode = shape.difference(wire)
            electrode = electrode.buffer(-beam_width / 2, cap_style="square", join_style="mitre")
            structures["electrode_groups"]["electrodes"].append(orient(electrode))

    # sort the shapes by channel number, not necessary but makes it easier to read
    structures["electrode_groups"]["electrodes"] = [x for _, x in sorted(zip(structures["electrode_groups"]["channel"],
                                                                             structures["electrode_groups"][
                                                                                 "electrodes"]))]
    structures["electrode_groups"]["electrodes_simple"] = [x for _, x in
                                                           sorted(zip(structures["electrode_groups"]["channel"],
                                                                      structures["electrode_groups"][
                                                                          "electrodes_simple"]))]
    structures["electrode_groups"]["original"] = [x for _, x in sorted(zip(structures["electrode_groups"]["channel"],
                                                                           structures["electrode_groups"]["original"]))]
    structures["electrode_groups"]["open"] = [x for _, x in sorted(zip(structures["electrode_groups"]["channel"],
                                                                       structures["electrode_groups"]["open"]))]
    structures["electrode_groups"]["channel"] = sorted(structures["electrode_groups"]["channel"])

    fig, ax = plt.subplots()
    # ax.plot(*line_left.xy, color='black')
    # ax.plot(*line_right.xy, color='black')

    # for structure in structures["pads"]:
    #     ax.plot(*structure.exterior.xy, color='tab:blue')
    # for structure in structures["electrode_groups"]["pads"]:
    #     ax.plot(*structure.exterior.xy, color='tab:orange')
    # for structure in structures["electrode_groups"]["electrodes_simple"]:
    #     ax.plot(*structure.exterior.xy, color='tab:green')
    for structure in structures["electrode_groups"]["electrodes"]:
        ax.plot(*structure.exterior.xy, color='tab:green')

    for void in voids:
        ax.plot(*void.exterior.xy, color='tab:green')
    for void in offset_shapes_1:
        ax.plot(*void.exterior.xy, color='tab:orange')
    for void in offset_shapes_2:
        ax.plot(*void.exterior.xy, color='tab:blue')

    # for void in voids:
    #     ax.plot(*void.exterior.xy, color='tab:green')
    #
    # ax.plot(*outside.exterior.xy, color='tab:blue')

    for structure in channels:
        center = structure[0].coords[0]
        channel = structure[1]
        ax.text(*center, s=channel, fontsize=8, ha='center', va='center')

    for structure in structures["electrode_groups"]["original"]:
        ax.plot(*structure.exterior.xy, color='tab:red')
    #     ax.plot(*structure.exterior.coords[-1], 'ro', markersize=4)
    #     ax.plot(*structure.exterior.coords[2], 'go', markersize=3)

    # ax.plot(*interior.exterior.xy)
    fig.show()

    print(f'Number of offset shapes: {len(offset_shapes_1)}, {len(offset_shapes_2)}')

    # write the shapes to a new dxf file
    # the original shapes are in white and in layer "mopa"
    # the voids are in cyan and in layer "voids"
    # the first offset shapes are in yellow and in layer "offset1"
    # the second offset shapes are in magenta and in layer "offset2"
    # the electrodes are in green and in layer "electrodes"
    # the annotations are in orange and in layer "annotations"

    doc = ezdxf.new()
    # create the layers and set the colors
    doc.layers.add('mopa', color=7)
    doc.layers.add('mopa_open', color=5)
    doc.layers.add('voids', color=4)
    doc.layers.add('offset1', color=2)
    doc.layers.add('offset2', color=6)
    doc.layers.add('electrodes', color=3)
    doc.layers.add('annotations', color=10)

    msp = doc.modelspace()

    counter = add_shapes_to_dxf(structures["electrode_groups"]["original"] + structures["pads"], msp, 'mopa')
    print(f'Number of original shapes saved: {counter}')

    counter = add_shapes_to_dxf(structures["electrode_groups"]["open"] +
                                [open_path(shape, pad=True) for shape in structures["pads"]], msp, 'mopa_open',
                                close=False)
    print(f'Number of open shapes saved: {counter}')

    # Place the text inside one of the two ground pads
    structures["pads"] = sorted(structures["pads"], key=lambda x: x.area, reverse=True)
    pads = structures["pads"][:2]
    # pick the pad at the bottom
    pad = sorted(pads, key=lambda x: x.centroid.y)[0]
    # offset the pad by 1 mm
    pad = pad.buffer(-1)
    x, y = pad.bounds[0], pad.bounds[1]

    font = FontFace('arial.ttf')
    translation = Matrix44.translate(x, y, 0)
    annotations = make_paths_from_str(filename + " - ", font=font, size=1.2, m=translation)
    for annotation in annotations:
        render_lwpolylines(msp, annotation, distance=0.1, dxfattribs={'layer': 'annotations'})

    counter = add_shapes_to_dxf(voids, msp, 'voids')
    print(f'Number of voids saved: {counter}')

    counter = add_shapes_to_dxf(offset_shapes_1, msp, 'offset1')
    print(f'Number of offset 1 shapes saved: {counter}')

    counter = add_shapes_to_dxf(offset_shapes_2, msp, 'offset2')
    print(f'Number of offset 2 shapes saved: {counter}')

    counter = add_shapes_to_dxf(structures["electrode_groups"]["electrodes"], msp, 'electrodes')
    print(f'Number of electrodes saved: {counter}')

    # set dxf units to mm
    doc.units = units.MM

    post_dxf = path_obj.with_name(f"{path_obj.stem}_post{path_obj.suffix}")
    doc.saveas(str(post_dxf))

    neighbors = []
    polygons = structures["electrode_groups"]["electrodes"]
    for i, poly in enumerate(polygons):
        poly = poly.buffer(beam_width).convex_hull
        for j, poly_ in enumerate(polygons):
            poly_ = poly_.buffer(beam_width).convex_hull
            if i != j and (poly.touches(poly_) or poly.intersects(poly_)):
                angle = np.arctan2(poly.centroid.x - poly_.centroid.x,
                                   poly.centroid.y - poly_.centroid.y)

                angle = abs(np.degrees(angle))
                if angle > 90:
                    angle = 180 - angle
                # if the angle is between 30 and 70 degrees, the polygons are connected diagonally
                # so the connections are excluded
                if angle < 30 or angle > 70:
                    neighbors.append((min(i, j), max(i, j)))
    # remove duplicates
    connections = [LineString([polygons[i].centroid, polygons[j].centroid])
                   for i, j in set(neighbors)]
    print(f'Number of neighbors: {len(connections)}')

    # save the udrop device file
    bounds = MultiPolygon(polygons).bounds
    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x
    height = max_y - min_y
    props = {"version": '1.2',
             "width": width,
             "height": height,
             # "viewBox": f'0,0,{width},{height}',
             "xmlns:inkscape": "http://www.inkscape.org/namespaces/inkscape",
             "xmlns:sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
             "xmlns": "http://www.w3.org/2000/svg",
             "xmlns:svg": "http://www.w3.org/2000/svg",
             "xmlns:rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
             "xmlns:cc": "http://creativecommons.org/ns#",
             "xmlns:dc": "http://purl.org/dc/elements/1.1/"
             }
    props = '\n\t' + '\n\t'.join([f'{key}="{value}"' for key, value in props.items()])
    svg = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
           f'<svg {props}>\n\t<defs\n\t\tid="defs2" />'
           '\n\t<g\n\t\tid="layer1"\n\t\tinkscape:groupmode="layer"\n\t\tinkscape:label="Device">'
           )

    svg_simple = svg
    channels = structures["electrode_groups"]["channel"]
    for i, electrode in enumerate(polygons):
        # transform the polygon
        shape = translate(electrode, -min_x, -min_y)
        # the svg coordinates are flipped in the y axis!
        shape = scale(shape, yfact=-1, origin=(0, height / 2))
        shape = orient(shape)
        d = shape.svg()
        d = 'd=' + d.split(' d=')[1][:-2]
        svg += (f'\n\t\t<path\n\t\t\t{d}' +
                f'\n\t\t\tid="electrode{i:03d}"' +
                f'\n\t\t\tstyle="fill:#0000ff;stroke-width:1.36000001"'
                f'\n\t\t\tdata-channels="{channels[i]}" />')
    svg += '\n\t</g>'

    for i, electrode in enumerate(structures["electrode_groups"]["electrodes_simple"]):
        # transform the polygon
        shape = translate(electrode, -min_x, -min_y)
        # the svg coordinates are flipped in the y axis!
        shape = scale(shape, yfact=-1, origin=(0, height / 2))
        shape = orient(shape)
        d = shape.svg()
        d = 'd=' + d.split(' d=')[1][:-2]
        svg_simple += (f'\n\t\t<path\n\t\t\t{d}' +
                       f'\n\t\t\tid="electrode{i:03d}"' +
                       f'\n\t\t\tstyle="fill:#0000ff;stroke-width:1.36000001"'
                       f'\n\t\t\tdata-channels="{channels[i]}" />')

    svg_simple += '\n\t</g>'

    svg_con = '\n\t<g\n\t\tid="layer2"\n\t\tinkscape:groupmode="layer"\n\t\tinkscape:label="Connections">'

    for i, line in enumerate(connections):
        line = translate(line, -min_x, -min_y)
        line = scale(line, yfact=-1, origin=(0, height / 2))
        x1, y1, x2, y2 = line.bounds
        svg_con += (f'\n\t\t<line\n\t\t\tx1="{x1}"\n\t\t\tx2="{x2}"\n\t\t\ty1="{y1}"\n\t\t\ty2="{y2}"'
                    f'\n\t\t\tid="line{i:03d}"'
                    f'\n\t\t\tstyle="fill:none;stroke:#000000;stroke-width:0.1" />')

    svg_con += '\n\t</g>\n</svg>'

    svg = svg + svg_con
    svg_simple = svg_simple + svg_con

    # create folder based on the file name next to the input file
    out_dir = path_obj.with_name(filename)
    out_dir_simple = path_obj.with_name(f"{filename}_simplified")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir_simple.mkdir(parents=True, exist_ok=True)

    with open(out_dir / 'device.svg', 'w') as f:
        f.write(svg.strip())
    with open(out_dir_simple / 'device.svg', 'w') as f:
        f.write(svg_simple.strip())


if __name__ == "__main__":
    dxf_post_process(path)
