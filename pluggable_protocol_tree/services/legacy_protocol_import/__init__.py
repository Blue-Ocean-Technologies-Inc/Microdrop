# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Import protocols authored in the Python 2 MicroDrop."""

from .conversion_report import ConversionReport
from .device_folder_scanner import (
    LegacyDeviceFolder, legacy_device_display_name, scan_for_device_folders,
)
from .device_svg_channel_map import read_device_svg_channel_map
from .legacy_pickle_reader import is_legacy_protocol_file, read_legacy_protocol
from .payload_builder import build_protocol_payload
from .protocol_converter import convert_legacy_protocol

__all__ = [
    "ConversionReport",
    "LegacyDeviceFolder",
    "build_protocol_payload",
    "convert_legacy_protocol",
    "is_legacy_protocol_file",
    "legacy_device_display_name",
    "read_device_svg_channel_map",
    "read_legacy_protocol",
    "scan_for_device_folders",
]
