import webbrowser
from pathlib import Path
from microdrop_utils._logger import get_logger

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