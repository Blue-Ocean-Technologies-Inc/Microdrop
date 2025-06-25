from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel

class ModePicker(QWidget):
    def __init__(self, route_model, electrodes_model):
        super().__init__()
        self.route_model = route_model
        self.electrodes_model = electrodes_model

        # Make checkable buttons
        self.button_draw = QPushButton("Draw")
        self.button_edit = QPushButton("Edit")
        self.button_autoroute = QPushButton("Autoroute")
        self.button_reset = QPushButton("Reset")

        # Layout
        layout = QHBoxLayout()
        for btn in (self.button_draw, self.button_edit, self.button_autoroute):
            btn.setCheckable(True)
            layout.addWidget(btn)
        layout.addWidget(self.button_reset) # Isn't checkable
        self.setLayout(layout)

        self.sync_buttons()

        self.button_draw.clicked.connect(lambda: self.set_mode("draw"))
        self.button_edit.clicked.connect(lambda: self.set_mode("edit"))
        self.button_autoroute.clicked.connect(lambda: self.set_mode("auto"))
        self.button_reset.clicked.connect(lambda: self.reset())

        self.route_model.observe(self.on_mode_changed, "mode")

    def sync_buttons(self):
        """Set checked states and label based on model.mode."""
        self.button_draw.setChecked(self.route_model.mode == "draw")
        self.button_edit.setChecked(self.route_model.mode == "edit")
        self.button_autoroute.setChecked(self.route_model.mode == "auto")

    def set_mode(self, mode):
        self.route_model.mode = mode

    def on_mode_changed(self, event):
        self.sync_buttons()

    def reset(self):
        self.electrodes_model.reset_states()
        self.route_model.reset()