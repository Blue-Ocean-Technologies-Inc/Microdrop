# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import logging
import re
from datetime import datetime

# Enthought library imports.
from pyface.api import GUI
from traits.api import (
    Bool,
    Enum,
    HasTraits,
    Instance,
    List,
    Property,
    Range,
    Str,
    cached_property,
    observe,
)

# Local imports.
from .consts import SEARCH_SCOPE_ALL, SEARCH_SCOPES
from .preferences import LoggerUIPreferences

# Compile the regex once at module level for performance
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def clean_ansi_text(text):
    """
    Strip ANSI codes from text
    """
    return ANSI_ESCAPE_PATTERN.sub("", text)


class LogMessage(HasTraits):
    """A single log entry formatted for the UI."""

    level = Enum("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    time = Str()
    message = Str()
    source = Str()


class LogModel(HasTraits):
    """Singleton model holding the list of logs."""

    #: SOURCE OF TRUTH — the buffered logs of the allowed levels, newest first.
    logs = List(Instance(LogMessage))

    #: The buffered logs matching the search, newest first — what the table
    #: shows. Searching only narrows this view, so clearing it loses nothing.
    shown_logs = List(Instance(LogMessage))

    #: Case-insensitive text a log must contain to be shown; "" shows all.
    search_text = Str()

    #: Which column ``search_text`` is matched against.
    search_scope = Enum(*SEARCH_SCOPES)

    buffer_size = Range(10, 100000, mode="spinner")

    # --- 1. Filter Checkboxes ---
    show_debug = Bool(True, label="Debug")
    show_info = Bool(True, label="Info")
    show_warning = Bool(True, label="Warning")
    show_error = Bool(True, label="Error")

    preferences = Instance(LoggerUIPreferences)

    allowed_logs = Property(
        List(Str),
        observe="show_debug, show_info, show_warning, show_error",
    )

    def traits_init(self):
        if self.preferences:
            self.buffer_size = self.preferences.buffer_size
            self.show_debug = self.preferences.show_debug
            self.show_info = self.preferences.show_info
            self.show_warning = self.preferences.show_warning
            self.show_error = self.preferences.show_error

    @cached_property
    def _get_allowed_logs(self):
        """Returns only the logs that match the selected checkboxes."""
        # Mapping standard Python logging string levels to our booleans
        # Adjust strings (e.g. 'WARN' vs 'WARNING') to match your record.levelname
        allowed = ["CRITICAL"]
        if self.show_debug:
            allowed.append("DEBUG")
        if self.show_info:
            allowed.append("INFO")
        if self.show_warning:
            allowed.extend(["WARNING", "WARN"])
        if self.show_error:
            allowed.extend(["ERROR"])

        # Return filtered list (deque converted to list)
        return allowed

    @observe("allowed_logs")
    def _allowed_logs_change(self, event):
        self.logs = [el for el in self.logs if el.level in self.allowed_logs]

    def add_log(self, record):
        dt = datetime.fromtimestamp(record.created)
        time_str = (
            dt.strftime("%Y-%m-%d %H:%M:%S") + f".{int(dt.microsecond / 1000):03d}"
        )

        msg = LogMessage(
            level=clean_ansi_text(record.levelname),
            time=time_str,
            message=clean_ansi_text(record.getMessage()),
            source=clean_ansi_text(record.name),
        )

        # we do not update list if the log is not allowed.
        if msg.level not in self.allowed_logs:
            return

        self.logs.insert(0, msg)

        if self._matches_search(msg):
            self.shown_logs.insert(0, msg)

        self._trim_to(self.buffer_size)

    def reset(self):
        """Clears all logs."""
        self.logs = []

    def _trim_to(self, size):
        """Drop the oldest logs beyond ``size``, from the shown ones too."""
        dropped_ids = {id(log) for log in self.logs[size:]}

        if not dropped_ids:
            return

        del self.logs[size:]

        # The shown logs keep the buffer's order, so the dropped ones that
        # matched are exactly at its tail.
        while self.shown_logs and id(self.shown_logs[-1]) in dropped_ids:
            self.shown_logs.pop()

    def _matches_search(self, log):
        """Return whether ``log`` contains the search text in the searched
        column(s)."""
        needle = self.search_text.strip().casefold()

        if not needle:
            return True

        if self.search_scope == SEARCH_SCOPE_ALL:
            fields = (log.source, log.message, log.level)
        else:
            fields = (getattr(log, self.search_scope.lower()),)

        return any(needle in field.casefold() for field in fields)

    @observe("logs, search_text, search_scope")
    def _refresh_shown_logs(self, event):
        self.shown_logs = [log for log in self.logs if self._matches_search(log)]

    @observe("buffer_size")
    def _buffer_size_changed(self, event):
        """
        Traits handler: Automatically trims the list if the user
        dynamically reduces the buffer size at runtime.
        """
        self._trim_to(event.new)

    @observe("[buffer_size, show_debug, show_info, show_warning, show_error]")
    def _save_preferences(self, event):
        self.preferences.trait_set(**{event.name: event.new})


class EnvisageLogHandler(logging.Handler):
    """
    Custom logging handler that pipes logs to the LogModel.
    """

    def __init__(self, _log_model_instance):
        super().__init__()
        self._log_model_instance = _log_model_instance

    def emit(self, record):
        # Python logging is thread-safe, but updating the UI/Traits is not.
        # We must push the update to the GUI thread.
        GUI.invoke_later(self._log_model_instance.add_log, record)
