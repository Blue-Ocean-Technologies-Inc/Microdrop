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
import webbrowser
from pathlib import Path
from shutil import copy2
from typing import Union

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


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
    failed write never truncates the file being replaced."""
    path = Path(path)
    partial_path = path.with_name(f"{path.name}.partial")

    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.write_bytes(content)

    os.replace(partial_path, path)


def open_file(filepath):
    if platform.system() == "Darwin":  # macOS
        subprocess.call(("open", filepath))
    elif platform.system() == "Windows":  # Windows
        os.startfile(filepath)
    else:  # linux variants
        subprocess.call(("xdg-open", filepath))
