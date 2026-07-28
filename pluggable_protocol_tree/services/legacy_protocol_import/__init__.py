"""Import protocols authored in the Python 2 MicroDrop."""

from .conversion_report import ConversionReport
from .device_folder_scanner import LegacyDeviceFolder, scan_for_device_folders
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
    "read_device_svg_channel_map",
    "read_legacy_protocol",
    "scan_for_device_folders",
]
