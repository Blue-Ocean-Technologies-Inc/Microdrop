# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Electrode-id -> channel map read straight from a device SVG.

Deliberately a local XML scan rather than a call into ``device_viewer``'s
SVG processor: reaching into another plugin is forbidden, and conversion
needs only the ``id`` and ``data-channels`` attributes -- no geometry.
"""

from xml.etree import ElementTree

from logger.logger_service import get_logger

logger = get_logger(__name__)

# SVG puts elements in a namespace; match any namespace on the local name.
_PATH_ELEMENT_TAG = "{*}path"
_CHANNEL_ATTRIBUTE = "data-channels"


def read_device_svg_channel_map(svg_path: str) -> dict:
    """Map every electrode id in ``svg_path`` to its channel number.

    Paths without an ``id``, without ``data-channels``, or whose channel is
    not a single integer are skipped -- decorative shapes and multi-channel
    annotations are not importable electrodes."""
    root = ElementTree.parse(svg_path).getroot()
    channel_map = {}
    # Element.iter() treats its argument as a literal tag and does not
    # understand the "{*}name" wildcard -- only the ElementPath-based
    # find/iterfind methods do, hence iterfind(".//...") here.
    for element in root.iterfind(f".//{_PATH_ELEMENT_TAG}"):
        electrode_id = element.attrib.get("id")
        raw_channel = element.attrib.get(_CHANNEL_ATTRIBUTE)
        if not electrode_id or not raw_channel:
            continue
        try:
            channel_map[electrode_id] = int(raw_channel)
        except ValueError:
            logger.debug(
                f"{svg_path!r}: electrode {electrode_id!r} has non-integer "
                f"{_CHANNEL_ATTRIBUTE}={raw_channel!r}; skipped")
    return channel_map
