# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Capture discovery for the image viewer: where the current experiment's
captures live, and the ordered list of those files. Pure path logic so it
stays hardware/Qt-free testable.
"""

# Standard library imports.
import calendar
import re
import time
from pathlib import Path

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from microdrop_application.helpers import get_current_experiment_directory

# Local imports.
from .consts import CAPTURE_TIMESTAMP_FORMAT, IMAGE_PATTERNS

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def current_captures_directory():
    """The captures folder of the CURRENT experiment (re-resolved on
    every call so experiment switches are picked up), or None when the
    experiment directory is unavailable (e.g. no Redis)."""
    try:
        return get_current_experiment_directory() / CAPTURES_DIR_NAME
    except Exception as e:
        logger.debug(f"Experiment directory unavailable: {e}")
        return None


def discover_experiments() -> list:
    """Every experiment folder alongside the current experiment:
    ``[(name, captures_path), ...]``, oldest first (by the folder's mtime).

    Rooted at the CURRENT experiment's parent (``get_current_experiment_
    directory().parent``) rather than a bare ``MicrodropPreferences()`` read
    — that instance returns the trait default, not the app's configured
    root, so it points at an empty folder. The parent of the folder the
    viewer already follows is exactly the Experiments root in use. Folders
    with no captures yet are still listed (selecting one just shows nothing)
    so the seek can walk them all. [] when the root is unavailable (no
    Redis)."""
    try:
        root = get_current_experiment_directory().parent
    except Exception as e:
        logger.debug(f"Experiments root unavailable: {e}")
        return []
    if not root.is_dir():
        return []
    experiments = [
        (child.name, child / CAPTURES_DIR_NAME)
        for child in root.iterdir()
        if child.is_dir()
    ]
    return sorted(
        experiments, key=lambda item: (item[1].parent.stat().st_mtime, item[0])
    )


def discover_captures(directory) -> list:
    """Every image (IMAGE_PATTERNS) under ``directory``, recursively,
    oldest first (save time, with the filename — which embeds a capture's
    UTC timestamp — as tiebreak). [] when the directory is unset or
    missing."""
    if directory is None or not Path(directory).is_dir():
        return []

    paths = {
        path for pattern in IMAGE_PATTERNS for path in Path(directory).rglob(pattern)
    }

    return sorted(paths, key=lambda path: (path.stat().st_mtime, path.name))


#: The Capture Session of images outside any session folder (the device
#: viewer's flat captures, the legacy flat ``captures/16bit_raw`` layout).
UNGROUPED_BURST = "ungrouped"

#: The Image Group of images saved straight into a session (or the
#: captures folder itself) rather than into a type subfolder.
NO_IMAGE_GROUP = "None"


def _session_folders(root):
    """Names of the first-level folders that are Capture Sessions: those
    holding subfolders (a capture-chain burst always holds its
    ``16bit_raw`` dir). A first-level folder of files only is an Image
    Group instead (e.g. the legacy flat ``captures/16bit_raw``)."""
    return {
        child.name
        for child in root.iterdir()
        if child.is_dir() and any(grand.is_dir() for grand in child.iterdir())
    }


def discover_image_groups(directory) -> dict:
    """The captures under ``directory`` by Image Group, each split into
    Capture Sessions: ``{image_group: [(session, [paths...]), ...]}``,
    sessions oldest first (by their first image's save time), images
    within a session oldest first. {} when the directory is unset or
    missing.

    An image's folders below ``directory`` place it: none -> no session,
    ``NO_IMAGE_GROUP``; a session folder first -> that session, with the
    folders below it (if any) as the group; otherwise the folders are the
    group, outside any session."""
    if directory is None or not Path(directory).is_dir():
        return {}

    root = Path(directory)
    sessions = _session_folders(root)
    groups: dict = {}

    for path in discover_captures(root):
        folders = path.relative_to(root).parts[:-1]

        if folders and folders[0] in sessions:
            session, group_folders = folders[0], folders[1:]
        else:
            session, group_folders = UNGROUPED_BURST, folders

        group = "/".join(group_folders) or NO_IMAGE_GROUP
        groups.setdefault(group, {}).setdefault(session, []).append(path)

    return {
        group: sorted(
            by_session.items(),
            key=lambda item: (item[1][0].stat().st_mtime, item[0]),
        )
        for group, by_session in groups.items()
    }


def merge_image_groups(image_groups) -> list:
    """Every Image Group's images merged per Capture Session — the "All"
    choice: ``[(session, [paths...]), ...]`` in discover_image_groups'
    order (sessions oldest first, images within a session oldest first)."""
    merged: dict = {}

    for sessions in image_groups.values():
        for session, paths in sessions:
            merged.setdefault(session, []).extend(paths)

    by_session = [
        (session, sorted(paths, key=lambda path: (path.stat().st_mtime, path.name)))
        for session, paths in merged.items()
    ]

    return sorted(by_session, key=lambda item: (item[1][0].stat().st_mtime, item[0]))


def sanitize_label(label: str) -> str:
    """A label reduced to a filename-safe form: alnum plus space/dash/
    underscore are kept, then spaces become underscores. An empty result
    falls back to "capture"."""
    clean = "".join(c for c in label if c.isalnum() or c in (" ", "-", "_")).strip()

    return clean.replace(" ", "_") or "capture"


def utc_stamp() -> str:
    """UTC timestamp in the shared capture-filename format."""
    return time.strftime(CAPTURE_TIMESTAMP_FORMAT, time.gmtime())


#: The utc_stamp() pattern as it appears inside capture filenames.
CAPTURE_TIMESTAMP_PATTERN = re.compile(r"\d{4}_\d{2}_\d{2}-\d{2}_\d{2}_\d{2}")

#: The standalone fluorescence app's stamp (dashes and underscores
#: swapped relative to utc_stamp's) — LOCAL time, which is the clock
#: that app wrote, where utc_stamp writes UTC.
LEGACY_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")
LEGACY_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


def capture_timestamp(path) -> float:
    """Capture time (epoch seconds) embedded in the filename by
    capture_service.utc_stamp() — or by the standalone app's local
    stamp, for folders imported from it — falling back to the file's
    mtime for names without a stamp or an impossible one (e.g. a
    mangled "13_45" month/day); 0.0 when neither exists."""
    name = Path(path).name
    match = CAPTURE_TIMESTAMP_PATTERN.search(name)
    if match:
        try:
            return float(
                calendar.timegm(time.strptime(match.group(0), CAPTURE_TIMESTAMP_FORMAT))
            )
        except ValueError:
            pass
    match = LEGACY_TIMESTAMP_PATTERN.search(name)
    if match:
        try:
            return time.mktime(time.strptime(match.group(0), LEGACY_TIMESTAMP_FORMAT))
        except (ValueError, OverflowError):
            pass
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0
