from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel

class ModePicker(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model

        # Make three checkable buttons
        self.button_draw = QPushButton("Draw")
        self.button_edit = QPushButton("Edit")
        self.button_autoroute = QPushButton("Autoroute")

        # Layout
        layout = QHBoxLayout()
        for btn in (self.button_draw, self.button_edit, self.button_autoroute):
            btn.setCheckable(True)
            layout.addWidget(btn)
        self.setLayout(layout)

        self.sync_buttons()

        self.button_draw.clicked.connect(lambda: self.set_mode("draw"))
        self.button_edit.clicked.connect(lambda: self.set_mode("edit"))
        self.button_autoroute.clicked.connect(lambda: self.set_mode("auto"))

        self.model.observe(self.on_mode_changed, "mode")

    def sync_buttons(self):
        """Set checked states and label based on model.mode."""
        self.button_draw.setChecked(self.model.mode == "draw")
        self.button_edit.setChecked(self.model.mode == "edit")
        self.button_autoroute.setChecked(self.model.mode == "auto")

    def set_mode(self, mode):
        self.model.mode = mode

    def on_mode_changed(self, event):
        self.sync_buttons()