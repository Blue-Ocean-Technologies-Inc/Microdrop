# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import os
import platform
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path
from shutil import copy2
from typing import Union

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: A swap onto a file locked by another process is tried this many times,
#: this far apart, before the error is raised.
ATOMIC_WRITE_ATTEMPTS = 5
ATOMIC_WRITE_RETRY_DELAY_S = 0.05


def open_html_in_browser(file_path):
    """Open an HTML file in the default web browser using pathlib."""
    # Convert file_path to a Path object
    path = Path(file_path)

    # Check if the file exists
    if path.exists() and path.is_file():
        # Open the file in the default web browser
        webbrowser.open_new_tab(path.resolve().as_uri())
    else:
        logger.error(f"File not found: {path}")


def next_free_numbered_path(path: Union[Path, str]) -> Path:
    """``path`` itself when nothing sits there, else the first free
    ``<stem> (N)<suffix>`` sibling (N starting at 2) -- the conventional
    don't-clobber rename for a second copy of the same name."""
    path = Path(path)
    if not path.exists():
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def safe_copy_file(
    src_file: Union[Path, str],
    dst_file: Union[Path, str],
):
    try:
        copy2(src_file, dst_file)
        logger.info(f"File '{dst_file}' was copied from {src_file}.")
        return dst_file

    except Exception as e:
        logger.error(f"Error loading file: {e}", exc_info=True)
        raise


def write_atomically(path, content):
    """Write ``content`` (bytes) to ``path`` aside, then swap it in, so a
    failed write never truncates the file being replaced.

    The aside file is unique and in the same directory, flushed to disk
    before the swap; a swap refused by a transient lock (an antivirus or
    indexer holding the file on Windows) is retried briefly. On any
    failure the aside file is removed and the error raised.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    descriptor, partial_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".partial"
    )
    partial_path = Path(partial_name)

    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

        _replace_with_retry(partial_path, path)

    except BaseException:
        partial_path.unlink(missing_ok=True)
        raise


def _replace_with_retry(source, destination):
    """``os.replace``, retried a few times while the destination is locked."""
    for attempt in range(ATOMIC_WRITE_ATTEMPTS):
        try:
            os.replace(source, destination)

            return

        except PermissionError:
            if attempt == ATOMIC_WRITE_ATTEMPTS - 1:
                raise

            time.sleep(ATOMIC_WRITE_RETRY_DELAY_S)


def open_file(filepath):
    if platform.system() == "Darwin":  # macOS
        subprocess.call(("open", filepath))
    elif platform.system() == "Windows":  # Windows
        os.startfile(filepath)
    else:  # linux variants
        subprocess.call(("xdg-open", filepath))
