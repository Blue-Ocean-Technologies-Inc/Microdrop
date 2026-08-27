# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""
Font path management for microdrop_style package.
One registry of the shipped font files, one path accessor, one loader.
"""

from pathlib import Path
from typing import Optional

from logger.logger_service import get_logger
from microdrop_utils.font_helpers import load_font_family

logger = get_logger(__name__)

# Get the package root directory
PACKAGE_ROOT = Path(__file__).parent

#: Every font file shipped with this package, keyed by the name accepted by
#: get_font_path / load_font_and_get_family, as a path relative to the package.
FONT_FILE_RELATIVE_PATHS = {
    "material_symbols": (
        "icons/Material_Symbols_Outlined/"
        "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf"
    ),
    "material_symbols_rounded": (
        "icons/Material_Symbols_Rounded/"
        "MaterialSymbolsRounded-VariableFont_FILL,GRAD,opsz,wght.ttf"
    ),
    "material_symbols_sharp": (
        "icons/Material_Symbols_Sharp/"
        "MaterialSymbolsSharp-VariableFont_FILL,GRAD,opsz,wght.ttf"
    ),
    "material_design_icons": (
        "icons/Material_Design_Icons/materialdesignicons-webfont.ttf"
    ),
    "inter": "fonts/Inter-VariableFont_opsz,wght.ttf",
    "inter_italic": "fonts/Inter-Italic-VariableFont_opsz,wght.ttf",
}


def get_font_path(font_name: str) -> Path:
    """
    Get the path to a font file by registry name.

    Args:
        font_name: A key of FONT_FILE_RELATIVE_PATHS
            (e.g. 'material_symbols', 'material_design_icons', 'inter')

    Returns:
        Path: Path to the requested font file

    Raises:
        ValueError: If the font name is not recognized
        FileNotFoundError: If the font file cannot be found
    """
    if font_name not in FONT_FILE_RELATIVE_PATHS:
        available_fonts = ", ".join(FONT_FILE_RELATIVE_PATHS.keys())
        raise ValueError(
            f"Unknown font name: {font_name}. Available fonts: {available_fonts}"
        )

    font_path = PACKAGE_ROOT / FONT_FILE_RELATIVE_PATHS[font_name]

    if not font_path.exists():
        raise FileNotFoundError(f"Font '{font_name}' not found at: {font_path}")

    return font_path


def load_font_and_get_family(font_name: str) -> Optional[str]:
    """
    Load a font by registry name into the QFontDatabase and return the font
    family name.

    Args:
        font_name: A key of FONT_FILE_RELATIVE_PATHS

    Returns:
        Optional[str]: Font family name if successful, None if failed
    """
    try:
        return load_font_family(get_font_path(font_name))
    except Exception as e:
        logger.error(f"Could not load font '{font_name}': {e}", exc_info=True)
        return None
