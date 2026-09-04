# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Turn whatever directory the user picked into legacy Device Folders.

Three shapes are accepted so the user never has to know which level of an
old MicroDrop tree to point at: a MicroDrop root (has ``devices/``), a
single Device Folder (has ``device.svg``), or a plain parent of Device
Folders.
"""

# Standard library imports.
import os

# Enthought library imports.
from traits.api import HasTraits, List, Str

# Local imports.
from .consts import (
    DEVICE_SVG_FILENAME,
    DEVICES_DIR_NAME,
    PROTOCOLS_DIR_NAME,
)
from .legacy_pickle_reader import is_legacy_protocol_file

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class LegacyDeviceFolder(HasTraits):
    """One old-MicroDrop Device Folder: its SVG and its importable protocols."""

    name = Str()
    device_svg_path = Str()
    protocol_paths = List(Str())


def _is_device_folder(path: str) -> bool:
    return os.path.isfile(os.path.join(path, DEVICE_SVG_FILENAME))


def legacy_device_display_name(device_svg_path: str) -> str:
    """The device name a legacy SVG path implies.

    Inside a Device Folder the SVG is always literally ``device.svg`` and
    the folder carries the device's name, so use the parent directory. A
    hand-picked SVG named anything else names the device itself."""
    path = os.path.normpath(device_svg_path)
    if os.path.basename(path) == DEVICE_SVG_FILENAME:
        return os.path.basename(os.path.dirname(path))
    return os.path.splitext(os.path.basename(path))[0]


def _protocol_paths_in(device_dir: str) -> list[str]:
    """Every file under ``protocols/`` that actually reads as a legacy
    protocol. Directory listings really do contain unrelated files."""
    protocols_dir = os.path.join(device_dir, PROTOCOLS_DIR_NAME)
    if not os.path.isdir(protocols_dir):
        return []
    try:
        entries = os.listdir(protocols_dir)
    except OSError as error:
        logger.warning(f"Could not list {protocols_dir!r}: {error}")
        return []
    candidates = sorted(os.path.join(protocols_dir, entry) for entry in entries)
    return [
        path
        for path in candidates
        if os.path.isfile(path) and is_legacy_protocol_file(path)
    ]


def _as_device_folder(device_dir: str) -> LegacyDeviceFolder:
    return LegacyDeviceFolder(
        name=os.path.basename(os.path.normpath(device_dir)),
        device_svg_path=os.path.join(device_dir, DEVICE_SVG_FILENAME),
        protocol_paths=_protocol_paths_in(device_dir),
    )


def _child_device_folders(parent_dir: str) -> list[LegacyDeviceFolder]:
    try:
        entries = os.listdir(parent_dir)
    except OSError as error:
        logger.warning(f"Could not list {parent_dir!r}: {error}")
        return []
    children = sorted(os.path.join(parent_dir, entry) for entry in entries)
    return [
        _as_device_folder(child)
        for child in children
        if os.path.isdir(child) and _is_device_folder(child)
    ]


def scan_for_device_folders(root_path: str) -> list[LegacyDeviceFolder]:
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
