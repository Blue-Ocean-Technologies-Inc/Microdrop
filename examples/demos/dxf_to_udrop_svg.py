import os
import ezdxf

import numpy as np

from ezdxf.upright import upright, upright_all
from shapely.geometry import LineString, Polygon
from shapely.affinity import scale, translate

path = "120-pin_v2.dxf"

def dxf_entity_to_points(entity_, circle_points=100):
    points = None
    if entity_.dxftype() == "LINE":
        points = np.array([entity_.dxf.start, entity_.dxf.end])
    elif entity_.dxftype() == "LWPOLYLINE":
        points = np.array(entity_.get_points())
    elif entity_.dxftype() == "ARC":
        start_angle = entity_.dxf.start_angle
        end_angle = entity_.dxf.end_angle
        radius = entity_.dxf.radius
        center = entity_.dxf.center
        points = np.array([center + radius * np.array([np.cos(start_angle), np.sin(start_angle)]),
                           center + radius * np.array([np.cos(end_angle), np.sin(end_angle)]),
                           center + radius * np.array([np.cos(start_angle + (end_angle - start_angle)/2),
                                                      np.sin(start_angle + (end_angle - start_angle)/2)])])
    elif entity_.dxftype() == "CIRCLE":
        center = entity_.dxf.center
        radius = entity_.dxf.radius
        points = np.array([center + radius * np.array([np.cos(angle), np.sin(angle)])
                           for angle in np.linspace(0, 2*np.pi, circle_points)])

    return points[...,:2]

def dxf_to_udrop_svg(path_, beam_width=0.1, force_connections=True, simplify_shapes=False):
    doc = ezdxf.readfile(path_)
    msp = doc.modelspace()
    upright_all(msp)
    device_with_wires = []
    udrop_device = []
    connections = []
    pads = []
    for entity in msp:
        if entity.dxf.layer == "0":
            device_with_wires.append(dxf_entity_to_points(entity))
        elif entity.dxf.layer.lower() == "electrodes" or entity.dxf.layer.lower() == "device":
            udrop_device.append(dxf_entity_to_points(entity))
        elif entity.dxf.layer.lower() == "pads":
            pads.append(dxf_entity_to_points(entity))
        elif entity.dxf.layer.lower() == "connections" and not force_connections:
            connections.append(dxf_entity_to_points(entity))

    print(f'Number of entities in layer 0: {len(device_with_wires)}')
    print(f'Number of entities in electrodes or device: {len(udrop_device)}')
    print(f'Number of entities in pads: {len(pads)}')

    wired_polygons = [Polygon(shape) for shape in device_with_wires]
    polygons = [Polygon(shape) for shape in udrop_device if len(shape) > 2]
    pad_polygons = [Polygon(shape) for shape in pads]
    if len(connections):
        connections = [LineString(line) for line in connections]

    # sort wired polygons by area to find the frame (reference polygon)
    ref_idx = np.argmax([poly.area for poly in wired_polygons])
    reference_polygon = wired_polygons.pop(ref_idx)

    # filter polygons outside the reference polygon
    polygons = [poly for poly in polygons if reference_polygon.contains(poly)]
    pad_polygons = [poly for poly in pad_polygons if reference_polygon.contains(poly)]

    # find neighbors
    if not len(connections):
        neighbors = []
        for i, poly in enumerate(polygons):
            poly = poly.buffer(beam_width)
            for j, poly_ in enumerate(polygons):
                poly_ = poly_.buffer(beam_width)
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
                     for i,j in set(neighbors)]
        print(f'Number of neighbors: {len(connections)}')

    """ Correlate the pads to a channel
        The pads are ordered from top left to bottom right.
        The standard uDrop device has 120 pads with 4 pads in each row.
        The pads are ordered as follows:
        59 58 57 56 ------ 63 62 61 60
        55 54 53 52 ------ 67 66 65 64
        ...
        7 6 5 4 ------ 112 113 114 115
        3 2 1 0 ------ 119 118 117 116
        
        uDrop pin map shows:
        116 117 118 119 ------ 0 1 2 3
        112 113 114 115 ------ 4 5 6 7
        ...
        60 61 62 63 ------ 56 57 58 59
    """
    # sort the pads by the y coordinate (right to left) to put them in 8 columns sorted by x coordinate (top to bottom)
    column_pads = sorted(pad_polygons, key=lambda x: x.centroid.x, reverse=True)
    column_pads = [sorted(column_pads[i:i+15], key=lambda x: x.centroid.y, reverse=True)
                   for i in range(0, len(column_pads), 15)]

    # assign a channel to each pad based on the position in the columns
    channels_per_pad = {}
    channels_per_wired = {}
    for idy, column in enumerate(column_pads):
        channel = 60 + idy
        if idy > 3:
            channel -= 8
        # if idy < 4:
        #     channel = 116 + idy
        # else:
        #     channel = idy - 4
        for idx, pad in enumerate(column):
            # if idy < 4:
            #     channel_ = channel - idx * 4
            # else:
            #     channel_ = channel + idx * 4
            if idy < 4:
                channel_ = channel + idx * 4
            else:
                channel_ = channel - idx * 4
            pad = column_pads[idy][idx]
            channels_per_pad[pad] = channel_

            for wired in wired_polygons:
                if wired.contains(pad)or wired.intersects(pad) or wired.touches(pad):
                    channels_per_wired[wired] = channel_
                    break

    # find the relationship between the polygons and the wired polygons
    relationships = []
    max_x,max_y = -np.inf, -np.inf
    min_x,min_y = np.inf, np.inf
    for poly in polygons:
        for wired in wired_polygons:
            if wired.contains(poly) or wired.intersects(poly) or wired.touches(poly):
                x_min_, y_min_, x_max_, y_max_ = poly.bounds
                if simplify_shapes:
                    c_x, c_y = poly.centroid.x, poly.centroid.y
                    side_x = x_max_ - x_min_
                    side_y = y_max_ - y_min_
                    xy_ratio = side_x / side_y
                    area = poly.area
                    # produce rectangles with the same area and aspect ratio
                    if xy_ratio > 1:
                        side_y = np.sqrt(area / xy_ratio)
                        side_x = xy_ratio * side_y
                    else:
                        side_x = np.sqrt(area * xy_ratio)
                        side_y = side_x / xy_ratio
                    poly = Polygon([(c_x - side_x/2, c_y - side_y/2),
                                    (c_x + side_x/2, c_y - side_y/2),
                                    (c_x + side_x/2, c_y + side_y/2),
                                    (c_x - side_x/2, c_y + side_y/2)])

                relationships.append([poly, channels_per_wired[wired]])
                max_x = max(max_x, x_max_)
                max_y = max(max_y, y_max_)
                min_x = min(min_x, x_min_)
                min_y = min(min_y, y_min_)
                break


    width = max_x - min_x
    height = max_y - min_y
    props = {"version": '1.2',
             "width": width,
             "height": height,
             # "viewBox": f'0,0,{width},{height}',
             "xmlns:inkscape":"http://www.inkscape.org/namespaces/inkscape",
             "xmlns:sodipodi":"http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
             "xmlns":"http://www.w3.org/2000/svg",
             "xmlns:svg":"http://www.w3.org/2000/svg",
             "xmlns:rdf":"http://www.w3.org/1999/02/22-rdf-syntax-ns#",
             "xmlns:cc":"http://creativecommons.org/ns#",
             "xmlns:dc":"http://purl.org/dc/elements/1.1/"
             }
    props = '\n\t' + '\n\t'.join([f'{key}="{value}"' for key, value in props.items()])
    svg = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
           f'<svg {props}>\n\t<defs\n\t\tid="defs2" />'
           '\n\t<g\n\t\tid="layer1"\n\t\tinkscape:groupmode="layer"\n\t\tinkscape:label="Device">'
           )

    for i, rel in enumerate(relationships):
        # transform the polygon
        shape = translate(rel[0], -min_x, -min_y)
        # the svg coordinates are flipped in the y axis!
        shape = scale(shape, yfact = -1, origin = (0, height/2))

        d = shape.svg()
        d = 'd=' + d.split(' d=')[1][:-2]
        svg += (f'\n\t\t<path\n\t\t\t{d}' +
                f'\n\t\t\tid="electrode{i:03d}"'+
                f'\n\t\t\tstyle="fill:#0000ff;stroke-width:1.36000001"'
                f'\n\t\t\tdata-channels="{rel[1]}" />')

    svg += '\n\t</g>'
    svg += '\n\t<g\n\t\tid="layer2"\n\t\tinkscape:groupmode="layer"\n\t\tinkscape:label="Connections">'

    for i, line in enumerate(connections):
        line = translate(line, -min_x, -min_y)
        line = scale(line, yfact=-1, origin=(0, height / 2))
        x1,y1,x2,y2 = line.bounds
        svg += (f'\n\t\t<line\n\t\t\tx1="{x1}"\n\t\t\tx2="{x2}"\n\t\t\ty1="{y1}"\n\t\t\ty2="{y2}"'
                f'\n\t\t\tid="line{i:03d}"'
                f'\n\t\t\tstyle="fill:none;stroke:#000000;stroke-width:0.1" />')

    svg += '\n\t</g>\n</svg>'

    # create folder based on the file name
    folder = path.split('.')[0]
    if simplify_shapes:
        folder += '_simplified'
    if not os.path.exists(folder):
        os.makedirs(folder)

    with open(folder + f'{os.sep}device.svg', 'w') as f:
        f.write(svg.strip())

dxf_to_udrop_svg(path)

