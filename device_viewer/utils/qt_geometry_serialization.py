# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""JSON (de)serialization of the Qt geometry the camera alignment persists."""

# Standard library imports.
import json
from typing import List, Tuple

# Enthought library imports.
from pyface.qt.QtCore import QPointF
from pyface.qt.QtGui import QTransform


def qtransform_serialize(transform: QTransform) -> str:
    return json.dumps(
        [
            transform.m11(),
            transform.m12(),
            transform.m13(),
            transform.m21(),
            transform.m22(),
            transform.m23(),
            transform.m31(),
            transform.m32(),
            transform.m33(),
        ]
    )


def qtransform_deserialize(data: str) -> QTransform:
    params = json.loads(data)
    return QTransform(
        params[0],
        params[1],
        params[2],
        params[3],
        params[4],
        params[5],
        params[6],
        params[7],
        params[8],
    )


def qpointf_list_serialize(list_qpointf: List[QPointF]) -> List[Tuple[float, float]]:
    return json.dumps([el.toTuple() for el in list_qpointf])


def qpointf_list_deserialize(data: str) -> List[QPointF]:
    return [QPointF(*coord_tuple) for coord_tuple in json.loads(data)]
