from pathlib import Path
import sys

def get_project_root():
    """Get the root directory of the Microdrop project."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent