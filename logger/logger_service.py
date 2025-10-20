import logging

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


# Create formatters
log_format = '%(asctime)s.%(msecs)03d [%(levelname)s:%(name)s]: %(message)s File "%(pathname)s", line %(lineno)d'
date_format = r'%Y-%m-%d %H:%M:%S'

# Create formatters
file_formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
console_formatter = ColoredFormatter(fmt=log_format, datefmt=date_format)

def get_logger(name, level=MIN_APP_LOGLEVEL, dev_mode=DEV_MODE):

    # Get the named logger
    logger = logging.getLogger(name)
    #
    # if dev_mode is given, set log level to given level
    if dev_mode:
        logger.setLevel(LEVELS[level])

    return logger