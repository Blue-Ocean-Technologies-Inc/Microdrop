import logging
import threading
import time

from .consts import (LOGGER_COLORS, LEVEL_COLORS, COLORS, MIN_APP_LOGLEVEL,
                     DEV_MODE, LEVELS, THIRD_PARTY_LOGGER_NAMES)

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

def init_logger(preferred_log_level=LEVELS["INFO"],
                file_handler=None,
                console_handler=None, console_handler_formatter=None):

    # setup console handler
    if not console_handler:
        console_handler = logging.StreamHandler()

    if not console_handler_formatter:
        console_handler_formatter = console_formatter

    console_handler.setFormatter(console_handler_formatter)

    # setup root logger:
    ROOT_LOGGER = logging.getLogger()
    ROOT_LOGGER.setLevel(preferred_log_level)

    # A debug switch should only make THIS repo's modules verbose: pin the
    # known third-party loggers to INFO so their internals (dramatiq enqueue
    # lines, apscheduler ticks, ...) don't flood the log.
    for third_party_name in THIRD_PARTY_LOGGER_NAMES:
        logging.getLogger(third_party_name).setLevel(
            max(logging.INFO, preferred_log_level))
    ROOT_LOGGER.handlers = []  # Clear existing handlers

    # if file handler provided, add to root logger.
    if file_handler:
        file_handler.setFormatter(file_formatter)
        ROOT_LOGGER.addHandler(file_handler)

    ROOT_LOGGER.addHandler(console_handler)

# ---------------------------------------------------------------------------
# Throttled debug: for log sites on hot message paths (router fan-out, actor
# publishes) where a streaming topic would otherwise emit hundreds of nearly
# identical lines per second.
# ---------------------------------------------------------------------------
_throttle_lock = threading.Lock()
_throttle_state = {}


def debug_throttled(logger, key, message, min_interval_s=2.0):
    """``logger.debug`` rate-limited per ``key``.

    Messages sharing a key (e.g. one key per topic) are emitted at most once
    per ``min_interval_s``; repeats in between are counted and reported on
    the next emission as ``(+N similar suppressed)``.
    """
    now = time.monotonic()
    state_key = (logger.name, key)
    with _throttle_lock:
        last_emit, suppressed = _throttle_state.get(state_key, (0.0, 0))
        if now - last_emit < min_interval_s:
            _throttle_state[state_key] = (last_emit, suppressed + 1)
            return
        _throttle_state[state_key] = (now, 0)
    if suppressed:
        message = f"{message} (+{suppressed} similar suppressed)"
    # stacklevel=2: attribute the record to the caller, not this helper.
    logger.debug(message, stacklevel=2)
