import os
import re
from pathlib import Path

from pyface.tasks.api import TraitsDockPane
from microdrop_application.dialogs.pyface_wrapper import information

from traits.trait_types import Instance, Dict, Int
from traitsui.api import View, Item
from traitsui.editors.tabular_editor import TabularEditor
from traitsui.qt.tabular_editor import TabularEditorEvent

from traitsui.api import TabularAdapter
from traits.api import observe

from .consts import LEVEL_COLORS, COLORS, LOGGER_COLORS, PKG

from logger.logger_service import get_logger
from .model import LogModel, _log_model_instance

logger = get_logger(__name__)

COLUMNS = [
        ('Time', 'time'),
        ('Level', 'level'),
        ('Source', 'source'),
        ('Message', 'message')
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
    scroll_index = Int()

    dclicked = Instance(TabularEditorEvent)

    def _model_default(self):
        return _log_model_instance

    # Define the View
    traits_view = View(
        Item(
            "object.logs",
            show_label=False,
            editor=TabularEditor(
                adapter=LogAdapter(),
                editable=False,
                selectable=False,
                auto_update=True,  # Updates UI immediately when logs are appended
                drag_move=False,
                dclicked="pane.dclicked",
                vertical_lines=False,
                horizontal_lines=False,
                scroll_to_row="pane.scroll_index",
            ),
            style_sheet=f"""
                        QTableView {{
                            background-color: #1e1f22; /* Dark Background */
                            color: {COLORS['RESET']}; 

                            /* Kill Selection Artifacts */
                            selection-background-color: transparent; 
                            outline: none;
                        }}

                        /* Ensure the header (if visible) matches or blends in */
                        QHeaderView::section {{
                            background-color: #1e1f22;
                            color: {COLORS['RESET']};
                            padding: 4px;
                        }}

                        /* Double-check to prevent item-level highlighting */
                        QTableView::item:selected, QTableView::item:hover {{
                            background-color: transparent;
                        }}
                    """,
        ),
        resizable=True,
    )

    @observe("dclicked")
    def _observe_event_dclicked(self, event):
        """
        On double-click:
        1. Find a file path or URL in the log message.
        2. If found, show an HTML dialog with a clickable link.
        """

        message = event.new.item.message

        # 2. Regex Patterns (Matches Windows/Linux paths and HTTP URLs)
        # Matches http:// or https://
        url_pattern = r"(https?://[^\s]+)"

        # Matches absolute paths: /home/user... or C:\Users...
        path_pattern = r"((?:/[^/\s]+)+/?|[a-zA-Z]:\\[^\s]+)"

        # 3. Find Matches
        # We strip trailing punctuation (like '.') so "file.txt." becomes "file.txt"
        potential_paths = [p.rstrip(".,;:") for p in re.findall(path_pattern, message)]
        urls = re.findall(url_pattern, message)

        # Combine them (URLs first, then Files)
        candidates = urls + potential_paths

        for candidate in candidates:
            # For files, verify existence before showing dialog
            is_file = False
            if not candidate.startswith("http"):
                if os.path.exists(candidate):
                    is_file = True
                else:
                    continue  # Skip invalid paths

            # 4. Prepare the Dialog
            item_type = "File" if is_file else "Link"

            # Convert local path to file URI for the HTML link
            if is_file:
                href = Path(candidate).as_uri()
            else:
                href = candidate

            # 5. Build HTML Message
            formatted_message = (
                f"<html>"
                f"<style>a {{ text-decoration: none; color: #0078d7; }}</style>"
                f"<p><b>{item_type} found in log:</b></p>"
                f"<p><a href='{href}'>{candidate}</a></p>"
                f"<br>"
                f"<small>Click the link above to open.</small>"
                f"</html>"
            )

            # 6. Show the Dialog
            information(
                None,
                formatted_message,
                title=f"Open {item_type}?",
            )

            # Stop after the first valid link found (prevent spamming dialogs)
            return

    # 3. Observer to update the scroll index when logs change
    @observe("model:logs.items")
    def _scroll_to_bottom(self, event):
        if self.model and self.model.logs:
            # Set the index to the last item in the list
            self.scroll_index = len(self.model.logs) - 1
