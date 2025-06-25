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

        # btn_layout
        btn_layout = QHBoxLayout()
        for btn in (self.button_draw, self.button_edit, self.button_autoroute):
            btn.setCheckable(True)
            btn_layout.addWidget(btn)
        btn_layout.addWidget(self.button_reset) # Isn't checkable
        
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
        self.button_reset.clicked.connect(lambda: self.reset())

        self.route_model.observe(self.on_mode_changed, "mode")

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        self.button_draw.setChecked(self.route_model.mode == "draw")
        self.button_edit.setChecked(self.route_model.mode == "edit")
        self.button_autoroute.setChecked(self.route_model.mode == "auto")
        self.mode_label.setText(f"Mode: {self.route_model.mode_name}")

    def set_mode(self, mode):
        self.route_model.mode = mode

    def on_mode_changed(self, event):
        self.sync_buttons_and_label()

    def reset(self):
        self.electrodes_model.reset_states()
        self.route_model.reset()