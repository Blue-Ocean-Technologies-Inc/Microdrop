import logging
from traits.api import HasTraits, List, Str, Instance, Enum
from pyface.api import GUI

import re
from datetime import datetime

# Compile the regex once at module level for performance
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

def clean_ansi_text(text):
    """
    Strip ANSI codes from text
    """
    return ANSI_ESCAPE_PATTERN.sub('', text)

class LogMessage(HasTraits):
    """A single log entry formatted for the UI."""
    level = Enum("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    time = Str()
    message = Str()
    source = Str()

class LogModel(HasTraits):
    """Singleton model holding the list of logs."""
    logs = List(Instance(LogMessage))

    def add_log(self, record):
        dt = datetime.fromtimestamp(record.created)
        time_str = (
            dt.strftime("%Y-%m-%d %H:%M:%S") + f".{int(dt.microsecond / 1000):03d}"
        )

        msg = LogMessage(
            level=clean_ansi_text(record.levelname),
            time=time_str,
            message=clean_ansi_text(record.getMessage()),
            source=clean_ansi_text(record.name)
        )

        self.logs.append(msg)

# Global instance to be shared between the Handler and the Plugin
_log_model_instance = LogModel()

class EnvisageLogHandler(logging.Handler):
    """
    Custom logging handler that pipes logs to the LogModel.
    """
    def emit(self, record):
        # Python logging is thread-safe, but updating the UI/Traits is not.
        # We must push the update to the GUI thread.
        GUI.invoke_later(_log_model_instance.add_log, record)
