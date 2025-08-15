from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel
from PySide6.QtGui import QFont
from pathlib import Path

from microdrop_style.icons.icons import ICON_AUTOMATION, ICON_DRAW, ICON_EDIT, ICON_RESET_WRENCH
from microdrop_style.colors import SECONDARY_SHADE, WHITE

MATERIAL_SYMBOLS_FONT_PATH = Path(__file__).parent.parent.parent.parent / "microdrop_style" / "icons" / "Material_Symbols_Outlined" / "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf"
ICON_FONT_FAMILY = "Material Symbols Outlined"

class CalibrationView(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model

        self.liquid_capacitance_label = QLabel()
        self.filler_capacitance_label = QLabel()
        self.capacitance_reset_button = QPushButton("refresh")
        self.capacitance_reset_button.setFont(QFont(ICON_FONT_FAMILY, 16))

        self.capacitance_reset_button.clicked.connect(self.reset_capacitance)
        self.model.observe(self.update_capacitance_labels, "liquid_capacitance")
        self.model.observe(self.update_capacitance_labels, "filler_capacitance")

        layout = QHBoxLayout()
        layout.addWidget(self.liquid_capacitance_label)
        layout.addWidget(self.filler_capacitance_label)
        layout.addWidget(self.capacitance_reset_button)
        self.setLayout(layout)

        self.update_capacitance_labels()

    def update_capacitance_labels(self, event=None):
        self.liquid_capacitance_label.setText(f"C_l: {self.model.liquid_capacitance if self.model.liquid_capacitance is not None else '-'} pF")
        self.filler_capacitance_label.setText(f"C_f: {self.model.filler_capacitance if self.model.filler_capacitance is not None else '-'} pF")

    def reset_capacitance(self):
        self.model.liquid_capacitance = None
        self.model.filler_capacitance = None
        