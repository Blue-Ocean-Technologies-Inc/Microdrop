from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel

from microdrop_style.colors import SECONDARY_SHADE, WHITE

ICON_FONT_FAMILY = "Material Symbols Outlined"

class CameraControlWidget(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model

        self.setStyleSheet(f"QPushButton {{ font-family: { ICON_FONT_FAMILY }; font-size: 22px; padding: 2px 2px 2px 2px; }} QPushButton:hover {{ color: { SECONDARY_SHADE[700] }; }} QPushButton:checked {{ background-color: { SECONDARY_SHADE[900] }; color: { WHITE }; }}")

        # Make checkable buttons
        self.button_align = QPushButton("view_in_ar")
        self.button_align.setToolTip("Align Camera")

        # btn_layout
        btn_layout = QHBoxLayout()
        for btn in [self.button_align]:
            btn.setCheckable(True)
            btn_layout.addWidget(btn)
        
        # Main layout
        layout = QVBoxLayout()

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.sync_buttons_and_label()

        self.button_align.clicked.connect(lambda: self.set_mode("camera-place"))
        self.model.observe(self.on_mode_changed, "mode")

    def on_mode_changed(self, event):
            self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        self.button_align.setChecked(self.model.mode == "camera-place")

    def set_mode(self, mode):
        self.model.mode = mode