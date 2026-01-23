import os
import re
from pathlib import Path
import html

from pyface.tasks.api import TraitsDockPane
from pyface.api import clipboard

from microdrop_application.dialogs.pyface_wrapper import information


from traitsui.api import (
    View,
    VGroup,
    HGroup,
    Item,
    TabularEditor,
    TabularAdapter,
    spring,
)
from traits.api import observe, Button, Instance, Dict, Int, Str, Range
from traitsui.qt.tabular_editor import TabularEditorEvent

from .consts import LEVEL_COLORS, COLORS, LOGGER_COLORS, PKG
from .model import LogModel

import logging
from logger.logger_service import get_logger
logger = get_logger(__name__)

from microdrop_utils.file_handler import open_file


COLUMNS = [
    ("Time", "time"),
    ("Level", "level"),
    ("Source", "source"),
    ("Message", "message"),
]


def get_log(object, row):
    return object.logs[row]


class LogAdapter(TabularAdapter):
    columns = COLUMNS
    _logger_colors = Dict()
    _color_index = Int(0)

    # --- 2. Text Color Logic ---
    def get_text_color(self, object, trait, row, column=0):
        level = get_log(object, row).level
        if COLUMNS[column][0] == "Level":
            return LEVEL_COLORS[level]

        elif COLUMNS[column][0] == "Source":
            source = object.logs[row].source
            # Assign a color to the logger name if it doesn't have one
            if source not in self._logger_colors:
                self._logger_colors[source] = LOGGER_COLORS[self._color_index]
                self._color_index = (self._color_index + 1) % len(LOGGER_COLORS)

            return self._logger_colors[source]

        else:
            return "#F9FAFB"

    # --- Tooltip Logic (Solves the "Long Message" issue) ---
    # When user hovers over the message column, show the full message
    def get_tooltip(self, object, trait, row, column):

        if not COLUMNS[column][0] == "Message":
            return

        log = get_log(object, row)

        return log.message


class LogPane(TraitsDockPane):
    """
    A Dock Pane that displays the logs in a table.
    """

    id = f"{PKG}.dock_pane"
    name = "Microdrop Console Logs"
    model = Instance(LogModel)

    clicked = Instance(TabularEditorEvent)
    dclicked = Instance(TabularEditorEvent)

    reset_button = Button("Reset Logs")
    copy_button = Button("Copy Log to Clipboard")
    show_button = Button("Open Log File")

    _current_message = Str()

    table_style_sheet = f"""
                        QTableView {{
                            background-color: #1e1f22; /* Dark Background */
                            color: {COLORS['RESET']}; 

                            /* Kill Selection Artifacts */
                            selection-color: white;
                            outline: none;
                        }}

                        /* Ensure the header (if visible) matches or blends in */
                        QHeaderView::section {{
                            background-color: #1e1f22;
                            color: {COLORS['WHITE']};
                            padding: 4px;
                        }}

                        /* Double-check to prevent item-level highlighting */
                        QTableView::item:selected {{
                            background-color: blue;
                        }}
                    """

    log_records_editor = TabularEditor(
        adapter=LogAdapter(),
        editable=False,
        auto_update=True,  # Updates UI immediately when logs are appended
        drag_move=False,
        dclicked="pane.dclicked",
        clicked="pane.clicked",
        vertical_lines=False,
        horizontal_lines=False,
    )

    # Define the View
    traits_view = View(
        VGroup(
            # --- Top: Filter Controls ---
            HGroup(
                Item("object.show_debug"),
                Item("object.show_info"),
                Item("object.show_warning"),
                Item("object.show_error"),
                label="Log Filters: ",
            ),
            # --- Middle: The Log Table ---
            Item(
                "object.logs",
                editor=log_records_editor,
                show_label=False,
                style_sheet=table_style_sheet,
            ),
            # --- Bottom: Controls ---
            HGroup(
                Item("pane.reset_button"),
                HGroup(Item("buffer_size", label="Buffer")),
                spring,
                Item("pane.show_button"),
                Item("pane.copy_button"),
                show_labels=False,
            ),
            show_labels=False,
        )
    )

    @observe("clicked")
    def _observe_event_clicked(self, event):
        log = event.new.item

        message = f"{log.time} [{log.level}:{log.source}]: {log.message}]"

        self._current_message = message

    @observe("dclicked")
    def _observe_event_dclicked(self, event):
        """
        On double-click:
        1. Always show the full log message.
        2. Automatically detect URLs or valid File Paths and turn them into HTML links.
        """
        log = event.new.item
        raw_message = log.message

        # 1. Escape HTML special chars so <Tags> don't break the view
        safe_message = html.escape(raw_message)

        # 2. Regex Strategy
        # We look for HTTP(s) links OR potential file paths
        # Pattern explanation: matches http://... OR (/path/... OR C:\path\...)
        combined_pattern = r"(https?://[^\s]+)|((?:/[^/\s]+)+/?|[a-zA-Z]:\\[^\s]+)"

        def link_replacer(match):
            """Helper to validate matches and wrap them in <a> tags."""
            text = match.group(0)

            # Strip trailing punctuation (e.g., "Check google.com.")
            clean_text = text.rstrip(".,;:\"'")
            trailing = text[len(clean_text) :]  # Keep the punctuation outside the link

            # Case A: Web URL
            if clean_text.startswith(("http:", "https:")):
                return f'<a href="{clean_text}">{clean_text}</a>{trailing}'

            # Case B: File Path
            # We only hyperlink it if the file actually exists on the user's disk
            if os.path.exists(clean_text):
                uri = Path(clean_text).as_uri()
                return f'<a href="{uri}">{clean_text}</a>{trailing}'

            # Case C: False positive (not a file, not a web link) -> Return text as is
            return text

        # 3. Inject Links
        # This replaces valid text with <a href="...">text</a>
        linked_message = re.sub(combined_pattern, link_replacer, safe_message)

        # 4. Build HTML
        html_content = (
            f"<html>"
            f"<style>"
            f"  body {{ font-family: sans-serif; margin: 0; }}"
            f"  a {{ text-decoration: none; color: #0078d7; font-weight: bold; }}"
            f"  .log-text {{ "
            f"      font-family: Consolas, 'Courier New', monospace; "
            f"      font-size: 14pt; "
            f"  }}"
            f"</style>"
            f"<body>"
            f"  <div class='log-text'>{linked_message}</div>"
            f"</body>"
            f"</html>"
        )

        # --- Prepare Metadata Header ---
        # formatted as: Time: <value>   Level: <value>   Source: <value>
        meta_html = (
            f"  <b>Time:</b> {log.time} <br>"
            f"  <b>Level:</b> {log.level} <br>"
            f"  <b>Source:</b> {log.source}"
        )

        # 5. Show Dialog (Always)
        information(
            None,
            meta_html,
            detail=html_content,
            detail_collapsible=False,
            title="Log Details",
        )

    ##---- Button handlers--------

    def _copy_button_fired(self):
        clipboard.text_data = self._current_message

    def _reset_button_fired(self):
        self.model.reset()

    def _show_button_fired(self):
        for handler in logging.getLogger().handlers[:]:  # Iterate on a copy!
            if isinstance(handler, logging.FileHandler):
                open_file(handler.baseFilename)

    @observe("model:buffer_size")
    def _buffer_size_changed(self, event):
        app = self.task.window.application
        app.preferences.set("microdrop.logger_ui.buffer_size", event.new)
