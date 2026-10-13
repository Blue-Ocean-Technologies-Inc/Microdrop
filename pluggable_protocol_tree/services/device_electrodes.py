# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free access to the active device's electrodes, read straight from its
SVG — the Fill Pattern dialog's fallback channel map and its channel
picker's geometry, without importing the device viewer's internals."""

# Microdrop package imports.
from device_viewer.consts import DEVICE_SVG_PATH_KEY
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop utils imports.
from microdrop_utils.svg_outline import SVGProcessor, is_device_layer

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def active_device_svg_path():
    """The active device SVG's path from app-globals, or '' when there is
    none or Redis is unreachable."""
    # Resolved per call, not at import: the dialog modules are imported by
    # tests and standalone prototypes that run without Redis.
    try:
        return get_microdrop_redis_globals_manager().get(DEVICE_SVG_PATH_KEY) or ""
    except Exception as exc:
        logger.warning(f"Could not read the active device SVG path: {exc}")

        return ""


def load_device_electrodes(svg_path):
    """{electrode id: ElectrodeData} of the Device layer of the SVG at
    ``svg_path``; {} when it has no Device layer."""
    processor = SVGProcessor(filename=str(svg_path))

    for child in processor.root:
        if is_device_layer(child):
            return processor.svg_to_electrodes(child)

    return {}


def active_device_electrode_channels():
    """{electrode id: channel} of the active device SVG's electrodes that
    have a channel; {} (with a warning) when it cannot be read."""
    svg_path = active_device_svg_path()

    if not svg_path:
        return {}

    try:
        electrodes = load_device_electrodes(svg_path)
    except Exception as exc:
        logger.warning(f"Could not read electrode channels from {svg_path}: {exc}")

        return {}

    return {
        electrode_id: electrode.channel
        for electrode_id, electrode in electrodes.items()
        if electrode.channel is not None
    }
