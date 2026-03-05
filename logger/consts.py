# This module's package.
import logging

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")


MIN_APP_LOGLEVEL = 'WARNING'
ROOT_LOGLEVEL = 'WARNING'

DEV_MODE = False

# ANSI color codes
COLORS = {
    'RESET': '\033[0m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'DEEP_RED': '\033[38;5;196m',  # Brighter red for critical
    'ORANGE': '\033[38;5;208m',    # Orange for warning
    'PURPLE': '\033[38;5;99m',     # Purple for debug
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

LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}