import os
import time
import json
import logging
from pathlib import Path


logging_config = {}
# Load logging configuration from logging.json
with open('logging.json', 'r') as f:
    logging_config = json.load(f)

# Set default logging level
LOGLEVEL = logging_config.get('default', 'INFO')

LOGFILE = f"application_logs{os.sep}application.log.{time.strftime('%Y-%m-%d_%H-%M-%S')}"

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


ROOT_LOGGER = logging.getLogger()
ROOT_LOGGER.setLevel(LEVELS[LOGLEVEL])

# Set logging levels for config
for logger_name, logger_level in logging_config.get('levels', {}).items():
    logging.getLogger(logger_name).setLevel(min(LEVELS[logger_level], LEVELS[LOGLEVEL])) # We want to set the level to the minimum of the logger level and the root level

for logger_name, logger_level in logging_config.get('ignore_default_level', {}).items():
    logging.getLogger(logger_name).setLevel(LEVELS[logger_level])

class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.logger_colors = {}
        self.color_index = 0

    def format(self, record):
        # Assign a color to the logger name if it doesn't have one
        if record.name not in self.logger_colors:
            self.logger_colors[record.name] = LOGGER_COLORS[self.color_index]
            self.color_index = (self.color_index + 1) % len(LOGGER_COLORS)

        # Add color to the logger name and level
        record.name = f"{self.logger_colors[record.name]}{record.name}{COLORS['RESET']}"
        record.levelname = f"{LEVEL_COLORS[record.levelname]}{record.levelname}{COLORS['RESET']}"
        
        return super().format(record)

def get_logger(name, log_file_path=LOGFILE):
    # Get the logging level for the logger from the config
    logger_level = logging_config.get('levels', {}).get(name, LOGLEVEL)

    # Set the level for the logger
    ROOT_LOGGER.setLevel(LEVELS[logger_level])

    Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d [%(levelname)s:%(name)s]: %(message)s '
        'File "%(pathname)s", line %(lineno)d',
        datefmt=r'%Y-%m-%d %H:%M:%S'
    )
    console_formatter = ColoredFormatter(
        '%(asctime)s.%(msecs)03d [%(levelname)s:%(name)s]: %(message)s '
        'File "%(pathname)s", line %(lineno)d',
        datefmt=r'%Y-%m-%d %H:%M:%S'
    )

    # Create handlers
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_handler.setFormatter(file_formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)

    # Configure root logger
    ROOT_LOGGER.handlers = []  # Clear existing handlers
    ROOT_LOGGER.addHandler(file_handler)
    ROOT_LOGGER.addHandler(console_handler)

    return logging.getLogger(name)