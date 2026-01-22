from pyface.tasks.api import TraitsDockPane
from traits.trait_types import Instance, Dict, Int
from traitsui.api import View, Item
from traitsui.editors.tabular_editor import TabularEditor
from traitsui.qt.tabular_editor import TabularEditorEvent

from traitsui.api import TabularAdapter
from traits.api import observe

from .consts import LEVEL_COLORS, COLORS, LOGGER_COLORS, PKG, PKG_name

from logger.logger_service import get_logger
from .model import LogModel, _log_model_instance

logger = get_logger(__name__)


def get_log(object, row):
    return object.logs[row]

class LogAdapter(TabularAdapter):
    columns = [
        ('Time', 'time'),
        ('Level', 'level'),
        ('Source', 'source'),
        ('Message', 'message')
    ]

    _logger_colors = Dict()
    _color_index = Int(0)

    # --- 2. Text Color Logic ---
    def get_text_color(self, object, trait, row, column=0):
        level = get_log(object, row).level
        if column == 1:
            return LEVEL_COLORS[level]

        elif column == 2:
            source = object.logs[row].source
            # Assign a color to the logger name if it doesn't have one
            if source not in self._logger_colors:
                self._logger_colors[source] = LOGGER_COLORS[self._color_index]
                self._color_index = (self._color_index + 1) % len(LOGGER_COLORS)

            return self._logger_colors[source]

        else:
            return "#F9FAFB"

    # --- Tooltip Logic (Solves the "Long Message" issue) ---
    # When user hovers over ANY column, show the full message
    def get_tooltip(self, object, trait, row, column):
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

    clicked = Instance(TabularEditorEvent)

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
                dclicked="pane.clicked",
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

    @observe("clicked")
    def observe_event_click_right(self, event):
        logger.critical(event)

    # 3. Observer to update the scroll index when logs change
    @observe("model:logs.items")
    def _scroll_to_bottom(self, event):
        if self.model and self.model.logs:
            # Set the index to the last item in the list
            self.scroll_index = len(self.model.logs) - 1
