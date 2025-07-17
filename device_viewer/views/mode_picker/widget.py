from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel
from PySide6.QtGui import QFont
from pathlib import Path

from microdrop_style.icons.icons import ICON_AUTOMATION, ICON_DRAW, ICON_EDIT, ICON_RESET_WRENCH
from microdrop_style.colors import SECONDARY_SHADE, WHITE

MATERIAL_SYMBOLS_FONT_PATH = Path(__file__).parent.parent.parent.parent / "microdrop_style" / "icons" / "Material_Symbols_Outlined" / "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf"
ICON_FONT_FAMILY = "Material Symbols Outlined"

def if_editable(func):
    """Decorator to check if the model is editable before executing the function."""
    def wrapper(self, *args, **kwargs):
        if not self.model.editable:
            self.sync_buttons_and_label()  # Ensure buttons and label are in sync with the model state
            return
        return func(self, *args, **kwargs)
    return wrapper

class ModePicker(QWidget):
    def __init__(self, model, pane):
        super().__init__()
        self.pane = pane
        self.model = model

        self.setStyleSheet(f"QPushButton {{ font-family: { ICON_FONT_FAMILY }; font-size: 22px; padding: 2px 2px 2px 2px; }} QPushButton:hover {{ color: { SECONDARY_SHADE[700] }; }} QPushButton:checked {{ background-color: { SECONDARY_SHADE[900] }; color: { WHITE }; }}")

        # Make checkable buttons
        self.button_draw = QPushButton(ICON_DRAW)
        self.button_draw.setToolTip("Draw")

        self.button_edit = QPushButton(ICON_EDIT)
        self.button_edit.setToolTip("Edit")

        self.button_autoroute = QPushButton(ICON_AUTOMATION)
        self.button_autoroute.setToolTip("Autoroute")

        self.button_reset_routes = QPushButton(ICON_RESET_WRENCH)
        self.button_reset_routes.setToolTip("Reset Routes")

        self.button_reset_electrodes = QPushButton("reset_settings") # TODO: Choose better icons for these buttons
        self.button_reset_electrodes.setToolTip("Reset Electrode States")

        self.button_channel_edit = QPushButton("Numbers")
        self.button_channel_edit.setToolTip("Edit Electrode Channels")

        self.button_undo = QPushButton("Undo")
        self.button_undo.setToolTip("Undo")

        self.button_redo = QPushButton("Redo")
        self.button_redo.setToolTip("Redo")

        # btn_layout
        btn_layout = QHBoxLayout()
        for btn in (self.button_draw, self.button_edit, self.button_autoroute, self.button_channel_edit):
            btn.setCheckable(True)
            btn_layout.addWidget(btn)
        btn_layout.addWidget(self.button_reset_routes)
        btn_layout.addWidget(self.button_reset_electrodes)
        btn_layout.addWidget(self.button_undo)
        btn_layout.addWidget(self.button_redo)
        
        # Main layout
        layout = QVBoxLayout()
        
        # Mode label
        self.mode_label = QLabel()
        layout.addWidget(self.mode_label)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.sync_buttons_and_label()

        self.button_draw.clicked.connect(lambda: self.set_mode("draw"))
        self.button_edit.clicked.connect(lambda: self.set_mode("edit"))
        self.button_autoroute.clicked.connect(lambda: self.set_mode("auto"))
        self.button_channel_edit.clicked.connect(lambda: self.set_mode("channel-edit"))
        self.button_reset_routes.clicked.connect(lambda: self.reset_routes())
        self.button_reset_electrodes.clicked.connect(lambda: self.reset_electrodes())
        self.button_undo.clicked.connect(lambda: self.undo())
        self.button_redo.clicked.connect(lambda: self.redo())
        self.model.observe(self.on_mode_changed, "mode")

    def on_mode_changed(self, event):
            self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        self.button_draw.setChecked(self.model.mode in ("draw", "edit-draw"))
        self.button_edit.setChecked(self.model.mode == "edit")
        self.button_autoroute.setChecked(self.model.mode == "auto")
        self.button_channel_edit.setChecked(self.model.mode == "channel-edit")
        self.mode_label.setText(f"Mode: {self.model.mode_name}")

    @if_editable
    def set_mode(self, mode):
        self.model.mode = mode

    @if_editable
    def undo(self):
        self.pane.undo()

    @if_editable
    def redo(self):
        self.pane.redo()

    @if_editable
    def reset_electrodes(self):
        self.model.reset_electrode_states()

    @if_editable
    def reset_routes(self):
        self.model.reset_route_manager()