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
from pathlib import Path

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


def _is_device_folder(path: Path) -> bool:
    return (path / DEVICE_SVG_FILENAME).is_file()


def legacy_device_display_name(device_svg_path: str) -> str:
    """The device name a legacy SVG path implies.

    Inside a Device Folder the SVG is always literally ``device.svg`` and
    the folder carries the device's name, so use the parent directory. A
    hand-picked SVG named anything else names the device itself."""
    path = Path(device_svg_path)
    if path.name == DEVICE_SVG_FILENAME:
        return path.parent.name
    return path.stem


def _sorted_children(directory: Path) -> list[Path]:
    """Everything directly under ``directory``, in a stable order.

    Sorted by string form rather than by ``Path``: PurePath ordering is
    case-insensitive on Windows, and these lists become dropdown entries,
    so the order has to be the same on every platform."""
    return sorted(directory.iterdir(), key=str)


def _protocol_paths_in(device_dir: Path) -> list[str]:
    """Every file under ``protocols/`` that actually reads as a legacy
    protocol. Directory listings really do contain unrelated files."""
    protocols_dir = device_dir / PROTOCOLS_DIR_NAME
    if not protocols_dir.is_dir():
        return []
    try:
        candidates = _sorted_children(protocols_dir)
    except OSError as error:
        logger.warning(f"Could not list {str(protocols_dir)!r}: {error}")
        return []
    return [
        str(path)
        for path in candidates
        if path.is_file() and is_legacy_protocol_file(str(path))
    ]


def _as_device_folder(device_dir: Path) -> LegacyDeviceFolder:
    return LegacyDeviceFolder(
        name=device_dir.name,
        device_svg_path=str(device_dir / DEVICE_SVG_FILENAME),
        protocol_paths=_protocol_paths_in(device_dir),
    )


def _child_device_folders(parent_dir: Path) -> list[LegacyDeviceFolder]:
    try:
        children = _sorted_children(parent_dir)
    except OSError as error:
        logger.warning(f"Could not list {str(parent_dir)!r}: {error}")
        return []
    return [
        _as_device_folder(child)
        for child in children
        if child.is_dir() and _is_device_folder(child)
    ]


def scan_for_device_folders(root_path: str) -> list[LegacyDeviceFolder]:
    """Device Folders reachable from ``root_path``, sorted by name.

    Returns an empty list rather than raising when the path is missing or
    holds nothing importable -- the dialog simply shows no devices."""
    root = Path(root_path) if root_path else None
    if root is None or not root.is_dir():
        logger.debug(f"{root_path!r} is not a directory; no devices found")
        return []
    devices_dir = root / DEVICES_DIR_NAME
    if devices_dir.is_dir():
        return _child_device_folders(devices_dir)
    if _is_device_folder(root):
        return [_as_device_folder(root)]
    return _child_device_folders(root)
