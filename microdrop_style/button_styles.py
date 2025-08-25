"""
Centralized button styling for Microdrop application.
Provides consistent button styles across all UI components.
"""

from .colors import (
    PRIMARY_SHADE, SECONDARY_SHADE, GREY, BLACK, WHITE
)

# Button dimensions and spacing
BUTTON_MIN_WIDTH = 40
BUTTON_MIN_HEIGHT = 26
BUTTON_BORDER_RADIUS = 4
BUTTON_PADDING = "4px 8px"
BUTTON_SPACING = 2

# Icon font family for buttons
ICON_FONT_FAMILY = "Material Symbols Outlined"

# Tooltip styles for consistency across all components
TOOLTIP_STYLE = f"""
QToolTip {{
    background-color: {GREY['dark']};
    color: {WHITE};
    padding: 6px 10px;
    font-size: 11pt;
    font-family: "Inter", sans-serif;
    border-radius: 6px;
    border: 1px solid {GREY['lighter']};
    max-width: 300px;
    text-align: center;
}}
"""

# Light mode tooltip styles
LIGHT_MODE_TOOLTIP_STYLE = f"""
QToolTip {{
    background-color: {WHITE};
    color: {BLACK};
    padding: 6px 10px;
    font-size: 11pt;
    font-family: "Inter", sans-serif;
    border-radius: 6px;
    border: 1px solid {GREY['light']};
    max-width: 300px;
    text-align: center;
}}
"""

# Dark mode tooltip styles
DARK_MODE_TOOLTIP_STYLE = f"""
QToolTip {{
    background-color: {GREY['dark']};
    color: {WHITE};
    padding: 6px 10px;
    font-size: 11pt;
    font-family: "Inter", sans-serif;
    border-radius: 6px;
    border: 1px solid {GREY['lighter']};
    max-width: 300px;
    text-align: center;
}}
"""

# Base button style (common to all themes)
BASE_BUTTON_STYLE = f"""
QPushButton {{ 
    font-family: {ICON_FONT_FAMILY}; 
    font-size: 22px; 
    padding: {BUTTON_PADDING};
    border-radius: {BUTTON_BORDER_RADIUS}px;
    min-width: {BUTTON_MIN_WIDTH}px;
    min-height: {BUTTON_MIN_HEIGHT}px;
    border: 1px solid transparent;
}} 

QPushButton:hover {{ 
    color: {SECONDARY_SHADE[700]}; 
    background-color: {GREY['light']};
    border-color: {SECONDARY_SHADE[300]};
}}

QPushButton:pressed {{
    background-color: {GREY['dark']};
}}

QPushButton:disabled {{
    opacity: 0.6;
}}

{TOOLTIP_STYLE}
"""

# Light mode button styles
LIGHT_MODE_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{ 
    background-color: {WHITE};
    color: {BLACK};
    border-color: {GREY['light']};
}}

QPushButton:disabled {{
    color: {GREY['dark']};
    background-color: {GREY['light']};
    border-color: {GREY['lighter']};
}}

{LIGHT_MODE_TOOLTIP_STYLE}
"""

# Dark mode button styles
DARK_MODE_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{ 
    background-color: {GREY['dark']};
    color: {WHITE};
    border-color: {GREY['lighter']};
}}

QPushButton:disabled {{
    color: {GREY['light']};
    background-color: {BLACK};
    border-color: {GREY['dark']};
}}

{DARK_MODE_TOOLTIP_STYLE}
"""

# Navigation button specific styles
NAVIGATION_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{
    font-size: 20px;
    min-width: 44px;
    min-height: 32px;
    padding: 6px 10px;
}}
"""

# Small button styles
SMALL_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{
    font-size: 18px;
    min-width: 32px;
    min-height: 24px;
    padding: 3px 6px;
}}
"""

# Large button styles
LARGE_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{
    font-size: 24px;
    min-width: 56px;
    min-height: 40px;
    padding: 8px 12px;
}}
"""

# Primary action button styles
PRIMARY_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{
    background-color: {PRIMARY_SHADE[600]};
    color: {WHITE};
    border-color: {PRIMARY_SHADE[700]};
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {PRIMARY_SHADE[700]};
    border-color: {PRIMARY_SHADE[800]};
}}

QPushButton:pressed {{
    background-color: {PRIMARY_SHADE[800]};
}}
"""

# Secondary action button styles
SECONDARY_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{
    background-color: {SECONDARY_SHADE[600]};
    color: {WHITE};
    border-color: {SECONDARY_SHADE[700]};
}}

QPushButton:hover {{
    background-color: {SECONDARY_SHADE[700]};
    border-color: {SECONDARY_SHADE[800]};
}}

QPushButton:pressed {{
    background-color: {SECONDARY_SHADE[800]};
}}
"""

# Danger/Error button styles
DANGER_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{
    background-color: #dc3545;
    color: {WHITE};
    border-color: #c82333;
}}

QPushButton:hover {{
    background-color: #c82333;
    border-color: #a71e2a;
}}

QPushButton:pressed {{
    background-color: #a71e2a;
}}
"""

# Success button styles
SUCCESS_BUTTON_STYLE = f"""
{BASE_BUTTON_STYLE}
QPushButton {{
    background-color: #28a745;
    color: {WHITE};
    border-color: #1e7e34;
}}

QPushButton:hover {{
    background-color: #1e7e34;
    border-color: #155724;
}}

QPushButton:pressed {{
    background-color: #155724;
}}
"""

# Function to get button style based on theme
def get_button_style(theme="light", button_type="default"):
    """
    Get button style based on theme and button type.
    
    Args:
        theme (str): 'light' or 'dark'
        button_type (str): 'default', 'navigation', 'small', 'large', 
                          'primary', 'secondary', 'danger', 'success'
    
    Returns:
        str: CSS stylesheet for the button
    """
    if theme == "dark":
        base_style = DARK_MODE_BUTTON_STYLE
    else:
        base_style = LIGHT_MODE_BUTTON_STYLE
    
    if button_type == "navigation":
        return NAVIGATION_BUTTON_STYLE
    elif button_type == "small":
        return SMALL_BUTTON_STYLE
    elif button_type == "large":
        return LARGE_BUTTON_STYLE
    elif button_type == "primary":
        return PRIMARY_BUTTON_STYLE
    elif button_type == "secondary":
        return SECONDARY_BUTTON_STYLE
    elif button_type == "danger":
        return DANGER_BUTTON_STYLE
    elif button_type == "success":
        return SUCCESS_BUTTON_STYLE
    else:
        return base_style


def get_tooltip_style(theme="light"):
    """
    Get tooltip style based on theme.
    
    Args:
        theme (str): 'light' or 'dark'
    
    Returns:
        str: CSS stylesheet for tooltips
    """
    if theme == "dark":
        return DARK_MODE_TOOLTIP_STYLE
    else:
        return LIGHT_MODE_TOOLTIP_STYLE


def get_complete_stylesheet(theme="light", button_type="default"):
    """
    Get complete stylesheet including buttons and tooltips.
    
    Args:
        theme (str): 'light' or 'dark'
        button_type (str): Button type for styling
    
    Returns:
        str: Complete CSS stylesheet
    """
    button_style = get_button_style(theme, button_type)
    tooltip_style = get_tooltip_style(theme)
    return f"{button_style}\n{tooltip_style}"

# Function to get button dimensions
def get_button_dimensions(button_type="default"):
    """
    Get button dimensions based on button type.
    
    Args:
        button_type (str): 'default', 'navigation', 'small', 'large'
    
    Returns:
        tuple: (min_width, min_height)
    """
    if button_type == "navigation":
        return (44, 32)
    elif button_type == "small":
        return (32, 24)
    elif button_type == "large":
        return (56, 40)
    else:
        return (BUTTON_MIN_WIDTH, BUTTON_MIN_HEIGHT)
