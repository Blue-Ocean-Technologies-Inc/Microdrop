"""
Font path management for microdrop_style package.
Provides clean, centralized access to font files without hardcoded paths.
"""

from pathlib import Path
from typing import Optional

# Get the package root directory
PACKAGE_ROOT = Path(__file__).parent

def get_material_symbols_font_path() -> Path:
    """
    Get the path to the Material Symbols Outlined font file.
    
    Returns:
        Path: Path to the MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf file
        
    Raises:
        FileNotFoundError: If the font file cannot be found
    """
    font_path = PACKAGE_ROOT / "icons" / "Material_Symbols_Outlined" / "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf"
    
    if not font_path.exists():
        raise FileNotFoundError(f"Material Symbols font not found at: {font_path}")
    
    return font_path

def get_material_symbols_rounded_font_path() -> Path:
    """
    Get the path to the Material Symbols Rounded font file.
    
    Returns:
        Path: Path to the MaterialSymbolsRounded-VariableFont_FILL,GRAD,opsz,wght.ttf file
        
    Raises:
        FileNotFoundError: If the font file cannot be found
    """
    font_path = PACKAGE_ROOT / "icons" / "Material_Symbols_Rounded" / "MaterialSymbolsRounded-VariableFont_FILL,GRAD,opsz,wght.ttf"
    
    if not font_path.exists():
        raise FileNotFoundError(f"Material Symbols Rounded font not found at: {font_path}")
    
    return font_path

def get_material_symbols_sharp_font_path() -> Path:
    """
    Get the path to the Material Symbols Sharp font file.
    
    Returns:
        Path: Path to the MaterialSymbolsSharp-VariableFont_FILL,GRAD,opsz,wght.ttf file
        
    Raises:
        FileNotFoundError: If the font file cannot be found
    """
    font_path = PACKAGE_ROOT / "icons" / "Material_Symbols_Sharp" / "MaterialSymbolsSharp-VariableFont_FILL,GRAD,opsz,wght.ttf"
    
    if not font_path.exists():
        raise FileNotFoundError(f"Material Symbols Sharp font not found at: {font_path}")
    
    return font_path

def get_inter_font_path() -> Path:
    """
    Get the path to the Inter font file.
    
    Returns:
        Path: Path to the Inter-VariableFont_opsz,wght.ttf file
        
    Raises:
        FileNotFoundError: If the font file cannot be found
    """
    font_path = PACKAGE_ROOT / "fonts" / "Inter-VariableFont_opsz,wght.ttf"
    
    if not font_path.exists():
        raise FileNotFoundError(f"Inter font not found at: {font_path}")
    
    return font_path

def get_inter_italic_font_path() -> Path:
    """
    Get the path to the Inter Italic font file.
    
    Returns:
        Path: Path to the Inter-Italic-VariableFont_opsz,wght.ttf file
        
    Raises:
        FileNotFoundError: If the font file cannot be found
    """
    font_path = PACKAGE_ROOT / "fonts" / "Inter-Italic-VariableFont_opsz,wght.ttf"
    
    if not font_path.exists():
        raise FileNotFoundError(f"Inter Italic font not found at: {font_path}")
    
    return font_path

def get_font_path(font_name: str) -> Path:
    """
    Get the path to a font file by name.
    
    Args:
        font_name: Name of the font (e.g., 'material_symbols', 'inter', 'inter_italic')
        
    Returns:
        Path: Path to the requested font file
        
    Raises:
        ValueError: If the font name is not recognized
        FileNotFoundError: If the font file cannot be found
    """
    font_mapping = {
        'material_symbols': get_material_symbols_font_path,
        'material_symbols_rounded': get_material_symbols_rounded_font_path,
        'material_symbols_sharp': get_material_symbols_sharp_font_path,
        'inter': get_inter_font_path,
        'inter_italic': get_inter_italic_font_path,
    }
    
    if font_name not in font_mapping:
        available_fonts = ', '.join(font_mapping.keys())
        raise ValueError(f"Unknown font name: {font_name}. Available fonts: {available_fonts}")
    
    return font_mapping[font_name]()

def load_material_symbols_font() -> Optional[str]:
    """
    Load the Material Symbols Outlined font and return the font family name.
    
    Returns:
        Optional[str]: Font family name if successful, None if failed
    """
    try:
        from microdrop_utils.font_helpers import load_font_family
        font_path = get_material_symbols_font_path()
        return load_font_family(font_path)
    except Exception:
        return None


def load_inter_font() -> Optional[str]:
    """
    Load the Inter font and return the font family name.
    
    Returns:
        Optional[str]: Font family name if successful, None if failed
    """
    try:
        from microdrop_utils.font_helpers import load_font_family
        font_path = get_inter_font_path()
        return load_font_family(font_path)
    except Exception:
        return None


def load_font_and_get_family(font_name: str) -> Optional[str]:
    """
    Load a font by name and return the font family name.
    
    Args:
        font_name: Name of the font (e.g., 'material_symbols', 'inter')
        
    Returns:
        Optional[str]: Font family name if successful, None if failed
    """
    try:
        from microdrop_utils.font_helpers import load_font_family
        font_path = get_font_path(font_name)
        return load_font_family(font_path)
    except Exception:
        return None
