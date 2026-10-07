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
import fnmatch
import os
import re
import threading
import time
from pathlib import Path

# Enthought library imports.
from traits.api import Any, Dict, Float, HasTraits, Set, Str

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from microdrop_application.helpers import get_current_experiment_directory

# Local imports.
from .consts import (
    CAPTURE_TIMESTAMP_FORMAT,
    DISCOVERY_FULL_WALK_INTERVAL_S,
    IMAGE_PATTERNS,
)

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

    images, _folder_mtimes, _sessions = _walk_captures(Path(directory))

    return [path for _mtime, _name, path in images]


def _walk_captures(root):
    """One ``os.scandir`` pass over ``root``, matching every IMAGE_PATTERNS
    pattern at once. Returns ``(images, folder_mtimes, sessions)``:

    - ``images``: ``(mtime, name, path)`` per image, oldest first;
    - ``folder_mtimes``: ``{folder: st_mtime_ns}`` for every folder walked,
      each read (with ``os.stat``, as the change check reads it) before
      the folder is listed, so a file landing mid-walk leaves a stale
      mtime behind and the next check walks again;
    - ``sessions``: names of the first-level folders that are Capture
      Sessions — those holding subfolders (a capture-chain burst always
      holds its ``16bit_raw`` dir). A first-level folder of files only is
      an Image Group instead (e.g. the legacy flat ``captures/16bit_raw``).
    """
    images = []
    folder_mtimes = {}
    sessions = set()

    # (folder, its name when it is a first-level folder, else None).
    pending = [(root, None)]

    while pending:
        folder, first_level_name = pending.pop()

        try:
            folder_mtimes[folder] = os.stat(folder).st_mtime_ns

            with os.scandir(folder) as entries:
                entries = list(entries)
        except OSError as error:
            # An unreadable or vanished subfolder only hides its own
            # images, as the recursive glob this replaces did.
            logger.debug(f"Skipping unreadable folder {folder}: {error}")
            continue

        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                first_level = entry.name if folder == root else None
                pending.append((Path(entry.path), first_level))

                if first_level_name is not None:
                    sessions.add(first_level_name)

            elif entry.is_file() and _is_image_name(entry.name):
                images.append((entry.stat().st_mtime, entry.name, Path(entry.path)))

    images.sort(key=lambda image: image[:2])

    return images, folder_mtimes, sessions


def _is_image_name(name):
    """Whether ``name`` matches an IMAGE_PATTERNS pattern (case-blind on
    Windows, like the filesystem)."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in IMAGE_PATTERNS)


#: The Capture Session of images outside any session folder (the device
#: viewer's flat captures, the legacy flat ``captures/16bit_raw`` layout).
UNGROUPED_BURST = "ungrouped"

#: The Image Group of images saved straight into a session (or the
#: captures folder itself) rather than into a type subfolder.
NO_IMAGE_GROUP = "None"


def file_signature(path):
    """``(size, mtime_ns)`` of a file — what changes while it is being
    written — or None when it cannot be read."""
    try:
        stat = Path(path).stat()
    except OSError:
        return None

    return stat.st_size, stat.st_mtime_ns


def _path_key(path):
    """``path`` spelled one way: the capture event and the folder walk
    may differ in slashes or (on Windows) case."""
    return os.path.normcase(str(Path(path)))


class CaptureReadiness(HasTraits):
    """Holds back capture files that may still be being written, so a
    discovery poll never offers a half-written PNG for loading.

    A file is ready once its mtime is at least ``settle_seconds`` old and
    its size and mtime match what the previous scan saw (a file new to
    this scan has nothing to match). A held-back file is offered on a
    later scan, once its writer has been quiet that long. Files their
    writer reports complete skip the wait.
    """

    #: How long a file must go unmodified before it counts as written —
    #: one discovery poll interval.
    settle_seconds = Float()

    #: path -> file_signature as the previous scan saw it.
    _previous = Dict()

    #: Paths their writer reported complete (the device viewer's capture
    #: event): ready at once.
    _complete = Set(Str)

    def mark_complete(self, path):
        self._complete.add(_path_key(path))

    def ready_paths(self, paths, now=None):
        """``paths`` (order kept) less those that may still be being
        written. One stat per path; remembers this scan's signatures for
        the next."""
        now = time.time() if now is None else now
        observed = {}
        ready = []

        for path in paths:
            signature = file_signature(path)

            if signature is None:
                continue

            observed[path] = signature

            if self._is_ready(path, signature, now):
                ready.append(path)

        self._previous = observed
        self._complete = {_path_key(path) for path in observed} & self._complete

        return ready

    def _is_ready(self, path, signature, now):
        if _path_key(path) in self._complete:
            return True

        _size, mtime_ns = signature
        settled = now - mtime_ns / 1e9 >= self.settle_seconds

        return settled and self._previous.get(path, signature) == signature


def discover_image_groups(directory, readiness=None) -> dict:
    """The captures under ``directory`` by Image Group, each split into
    Capture Sessions: ``{image_group: [(session, [paths...]), ...]}``,
    sessions oldest first (by their first image's save time), images
    within a session oldest first. {} when the directory is unset or
    missing. A :class:`CaptureReadiness` leaves out files that may still
    be being written.

    An image's folders below ``directory`` place it: none -> no session,
    ``NO_IMAGE_GROUP``; a session folder first -> that session, with the
    folders below it (if any) as the group; otherwise the folders are the
    group, outside any session."""
    if directory is None or not Path(directory).is_dir():
        return {}

    root = Path(directory)
    image_groups, _folder_mtimes = _image_groups_of(root, readiness)

    return image_groups


def _image_groups_of(root, readiness=None):
    """discover_image_groups for an existing ``root``, plus the walk's
    ``folder_mtimes``."""
    images, folder_mtimes, sessions = _walk_captures(root)
    saved_at = {}
    groups: dict = {}

    if readiness is not None:
        ready = set(readiness.ready_paths([image[2] for image in images]))
        images = [image for image in images if image[2] in ready]

    for mtime, _name, path in images:
        saved_at[path] = mtime
        folders = path.relative_to(root).parts[:-1]

        if folders and folders[0] in sessions:
            session, group_folders = folders[0], folders[1:]
        else:
            session, group_folders = UNGROUPED_BURST, folders

        group = "/".join(group_folders) or NO_IMAGE_GROUP
        groups.setdefault(group, {}).setdefault(session, []).append(path)

    image_groups = {
        group: sorted(
            by_session.items(),
            key=lambda item: (saved_at[item[1][0]], item[0]),
        )
        for group, by_session in groups.items()
    }

    return image_groups, folder_mtimes


class CaptureFolderWatch(HasTraits):
    """discover_image_groups for a polled folder that skips the walk while
    no folder under it has changed — one stat per folder instead of a
    listing of every file.

    A folder's mtime moves when entries are added to, removed from or
    renamed in it, NOT when a file's contents change: a file rewritten in
    place keeps its old save time (and place in the order) until the next
    walk. Some filesystems never move it at all, hence a walk at least
    every ``full_walk_interval_s`` regardless. Thread-safe: the discovery
    worker and a direct rescan may share one.
    """

    #: Longest the cached result is reused without a walk (s).
    full_walk_interval_s = Float(DISCOVERY_FULL_WALK_INTERVAL_S)

    #: The folder the cached result is for (None before the first walk).
    _root = Any(None)

    #: Every folder of the last walk -> its st_mtime_ns at the time.
    _folder_mtimes = Dict()

    #: The last walk's discover_image_groups result.
    _image_groups = Any()

    #: time.monotonic() of the last walk.
    _walked_at = Float()

    _lock = Any()

    def __lock_default(self):
        return threading.Lock()

    def image_groups(self, directory, readiness=None):
        """discover_image_groups(``directory``, ``readiness``), reusing
        the last result (the same object) while nothing under it has
        changed."""
        if directory is None or not Path(directory).is_dir():
            return {}

        root = Path(directory)

        with self._lock:
            if not self._is_unchanged(root):
                self._image_groups, self._folder_mtimes = _image_groups_of(
                    root, readiness
                )
                self._root = root
                self._walked_at = time.monotonic()

            return self._image_groups

    def _is_unchanged(self, root):
        if root != self._root:
            return False

        if time.monotonic() - self._walked_at >= self.full_walk_interval_s:
            return False

        for folder, mtime_ns in self._folder_mtimes.items():
            try:
                if os.stat(folder).st_mtime_ns != mtime_ns:
                    return False
            except OSError:
                return False

        return True


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
