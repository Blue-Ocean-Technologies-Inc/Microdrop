import webbrowser
from pathlib import Path
from shutil import copy2
from typing import Union
import subprocess
import os
import platform

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


def safe_copy_file(src_file: Union[Path, str], dst_file: Union[Path, str], ):
    try:
        copy2(src_file, dst_file)
        logger.info(f"File '{dst_file}' was copied from {src_file}.")
        return dst_file

    except Exception as e:
        logger.error(f"Error loading file: {e}", exc_info=True)
        raise

def open_file(filepath):
    if platform.system() == "Darwin":  # macOS
        subprocess.call(("open", filepath))
    elif platform.system() == "Windows":  # Windows
        os.startfile(filepath)
    else:  # linux variants
        subprocess.call(("xdg-open", filepath))
