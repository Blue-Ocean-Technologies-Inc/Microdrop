# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

COLORS = {
    'RESET': "#ABB2BF",         # Resets to default
    'RED': '#CD0000',      # Standard ANSI Red
    'GREEN': '#00CD00',    # Standard ANSI Green
    'YELLOW': '#CDCD00',   # Standard ANSI Yellow
    'BLUE': '#1E90FF',
    'MAGENTA': '#CD00CD',  # Standard ANSI Magenta
    'CYAN': '#00CDCD',     # Standard ANSI Cyan
    'WHITE': '#E5E5E5',    # Standard ANSI White (Light Gray)
    'DEEP_RED': '#FF0000', # Xterm color 196
    'ORANGE': '#FF8700',   # Xterm color 208
    'PURPLE': '#875FFF',   # Xterm color 99
}

# List of colors to cycle through for different logger names
LOGGER_COLORS = [COLORS['GREEN'], COLORS['BLUE'], COLORS['MAGENTA'],
                COLORS['CYAN'], COLORS['YELLOW']]

# Colors for different log levels
LEVEL_COLORS = {
    'DEBUG': COLORS['PURPLE'],
    'INFO': COLORS['GREEN'],
    'WARNING': COLORS['ORANGE'],
    'ERROR': COLORS['RED'],
    'CRITICAL': COLORS['DEEP_RED']
}
