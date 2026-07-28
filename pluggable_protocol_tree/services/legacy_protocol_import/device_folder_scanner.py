"""Turn whatever directory the user picked into legacy Device Folders.

Three shapes are accepted so the user never has to know which level of an
old MicroDrop tree to point at: a MicroDrop root (has ``devices/``), a
single Device Folder (has ``device.svg``), or a plain parent of Device
Folders.
"""

import os

from traits.api import HasTraits, List, Str

from logger.logger_service import get_logger

from .consts import (
    DEVICE_SVG_FILENAME, DEVICES_DIR_NAME, PROTOCOLS_DIR_NAME,
)
from .legacy_pickle_reader import is_legacy_protocol_file

logger = get_logger(__name__)


class LegacyDeviceFolder(HasTraits):
    """One old-MicroDrop Device Folder: its SVG and its importable protocols."""

    name = Str()
    device_svg_path = Str()
    protocol_paths = List(Str())


def _is_device_folder(path: str) -> bool:
    return os.path.isfile(os.path.join(path, DEVICE_SVG_FILENAME))


def _protocol_paths_in(device_dir: str) -> list:
    """Every file under ``protocols/`` that actually reads as a legacy
    protocol. Directory listings really do contain unrelated files."""
    protocols_dir = os.path.join(device_dir, PROTOCOLS_DIR_NAME)
    if not os.path.isdir(protocols_dir):
        return []
    candidates = sorted(os.path.join(protocols_dir, entry)
                        for entry in os.listdir(protocols_dir))
    return [path for path in candidates
            if os.path.isfile(path) and is_legacy_protocol_file(path)]


def _as_device_folder(device_dir: str) -> LegacyDeviceFolder:
    return LegacyDeviceFolder(
        name=os.path.basename(os.path.normpath(device_dir)),
        device_svg_path=os.path.join(device_dir, DEVICE_SVG_FILENAME),
        protocol_paths=_protocol_paths_in(device_dir),
    )


def _child_device_folders(parent_dir: str) -> list:
    children = sorted(os.path.join(parent_dir, entry)
                      for entry in os.listdir(parent_dir))
    return [_as_device_folder(child) for child in children
            if os.path.isdir(child) and _is_device_folder(child)]


def scan_for_device_folders(root_path: str) -> list:
    """Device Folders reachable from ``root_path``, sorted by name.

    Returns an empty list rather than raising when the path is missing or
    holds nothing importable -- the dialog simply shows no devices."""
    if not root_path or not os.path.isdir(root_path):
        logger.debug(f"{root_path!r} is not a directory; no devices found")
        return []
    devices_dir = os.path.join(root_path, DEVICES_DIR_NAME)
    if os.path.isdir(devices_dir):
        return _child_device_folders(devices_dir)
    if _is_device_folder(root_path):
        return [_as_device_folder(root_path)]
    return _child_device_folders(root_path)
