from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSizePolicy


class CalibrationView(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model

        self.liquid_capacitance_label = QLabel()
        self.filler_capacitance_label = QLabel()
        self.capacitance_reset_button = QPushButton("refresh")
        self.capacitance_reset_button.setToolTip("Reset capacitance calibration values")

        self.capacitance_reset_button.clicked.connect(self.reset_capacitance)
        self.model.observe(self.update_capacitance_labels, "liquid_capacitance_over_area")
        self.model.observe(self.update_capacitance_labels, "filler_capacitance_over_area")

        layout = QHBoxLayout()
        layout.addWidget(self.liquid_capacitance_label)
        layout.addWidget(self.filler_capacitance_label)
        layout.addWidget(self.capacitance_reset_button)
        layout.addStretch()  # Add stretch to push widgets to the left and expand the layout
        self.setLayout(layout)
        
        # Set size policy to allow horizontal expansion but keep natural height
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.update_capacitance_labels()

    def update_capacitance_labels(self, event=None):
        self.liquid_capacitance_label.setText(f"C_l: {self.model.liquid_capacitance_over_area:.4f} pF/mm^2" if self.model.liquid_capacitance_over_area is not None else 'C_l: -')
        self.filler_capacitance_label.setText(f"C_f: {self.model.filler_capacitance_over_area:.4f} pF/mm^2" if self.model.filler_capacitance_over_area is not None else 'C_f: -')

    def reset_capacitance(self):
        self.model.liquid_capacitance_over_area = None
        self.model.filler_capacitance_over_area = None
        