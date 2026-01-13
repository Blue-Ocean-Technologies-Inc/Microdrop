from microdrop_style.helpers import get_complete_stylesheet, is_dark_mode
from protocol_grid.consts import (
    step_defaults,
    group_defaults,
    ROW_TYPE_ROLE,
    GROUP_TYPE,
    STEP_TYPE,
)
from protocol_grid.state.protocol_state import ProtocolStep, ProtocolGroup

import sys
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QApplication,
    QMainWindow,
    QVBoxLayout,
)

# Assuming these imports work in your environment
from microdrop_style.font_paths import load_material_symbols_font, load_inter_font

# from microdrop_style.helpers import style_app
# from protocol_grid.consts import step_defaults, group_defaults, ROW_TYPE_ROLE, GROUP_TYPE
# from protocol_grid.state.protocol_state import ProtocolStep, ProtocolGroup
# from protocol_grid.widget import PGCWidget


quick_protocol_actions = [
    ("add_step", "add", "Add step below selection"),
    ("delete_row", "delete", "Delete selected step / group"),
    ("add_group", "playlist_add", "Add group"),
    ("import_protocol", "unarchive", "Import protocol to selected group"),
    ("open_protocol", "file_open", "Open Protocol"),
    ("save_protocol", "save", "Save Protocol"),
    ("new_protocol", "new_window", "New protocol"),
]


class QuickProtocolActions(QHBoxLayout):

    def __init__(self):
        super().__init__()

        self.actions = {}

        def _add_button(id, text, tooltip):
            button = QPushButton(text)
            button.setToolTip(tooltip)

            setattr(self, id, button)
            self.actions[id] = button

            self.addWidget(button)

        for id, text, tooltip in [
            ("add_step", "add", "Add step below selection"),
            ("delete_row", "delete", "Delete selected step / group"),
            ("add_group", "playlist_add", "Add group"),
            ("import_protocol", "unarchive", "Import protocol to selected group"),
            ("open_protocol", "file_open", "Open Protocol"),
            ("save_protocol", "save", "Save Protocol"),
            ("new_protocol", "new_window", "New protocol"),
        ]:

            _add_button(id, text, tooltip)

        self.addStretch()


class QuickProtocolActionsController:

    def __init__(self, view, protocol_grid: "PGCWidget"):
        self.view = view
        self.protocol_grid = protocol_grid

        self.view.actions["add_step"].clicked.connect(self.protocol_grid.add_step)

        self.view.actions["delete_row"].clicked.connect(
            self.protocol_grid._protected_delete_selected
        )
        self.view.actions["add_group"].clicked.connect(self.protocol_grid.add_group)

        self.view.actions["import_protocol"].clicked.connect(
            self.protocol_grid.import_into_json
        )
        self.view.actions["open_protocol"].clicked.connect(
            self.protocol_grid.import_from_json
        )
        self.view.actions["save_protocol"].clicked.connect(
            self.protocol_grid.export_to_json
        )
        self.view.actions["new_protocol"].clicked.connect(
            self.protocol_grid.new_protocol
        )


    def on_selection_changed(self):
        if (
            hasattr(self.protocol_grid, "_processing_device_viewer_message")
            and self.protocol_grid._processing_device_viewer_message
        ):
            return
        if self.protocol_grid._programmatic_change:
            return
        if (
            hasattr(self.protocol_grid, "_restoring_selection")
            and self.protocol_grid._restoring_selection
        ):
            return
        if self.protocol_grid._protocol_running:
            return
        selected_paths = self.protocol_grid.get_selected_paths()

        has_selection = len(selected_paths) > 0
        if not self.protocol_grid._protocol_running:
            self.view.actions["import_protocol"].setEnabled(has_selection)

    def _update_ui_enabled_state(self, enabled):
        for id in [el[0] for el in quick_protocol_actions]:
            getattr(self.view, id).setEnabled(enabled)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Load Global App Font (Inter)
    LABEL_FONT_FAMILY = load_inter_font()
    app.setFont(QFont(LABEL_FONT_FAMILY, 11))

    # 2. Ensure Material Symbols are loaded
    # (The class now handles fetching the specific name for the buttons)
    load_material_symbols_font()

    window = QMainWindow()
    central_widget = QWidget()

    central_widget.setLayout(QuickProtocolActions())

    central_widget.setStyleSheet(
        get_complete_stylesheet(theme="dark" if is_dark_mode() else "light")
    )

    window.setCentralWidget(central_widget)

    window.setCentralWidget(central_widget)
    window.resize(400, 100)
    window.show()
    sys.exit(app.exec())
