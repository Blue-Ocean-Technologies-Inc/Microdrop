from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel, QSizePolicy
from pathlib import Path

from microdrop_style.button_styles import get_complete_stylesheet
from microdrop_style.font_paths import load_material_symbols_font

# Load the Material Symbols font using the clean API
ICON_FONT_FAMILY = load_material_symbols_font() or "Material Symbols Outlined"


class CalibrationView(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model

        self.liquid_capacitance_label = QLabel()
        self.filler_capacitance_label = QLabel()
        self.capacitance_reset_button = QPushButton("refresh")
        self.capacitance_reset_button.setToolTip("Reset capacitance calibration values")
        
        # Apply theme-aware styling AFTER creating the button
        self._apply_theme_styling()

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

    def _apply_theme_styling(self):
        """Apply theme-aware styling to the widget."""
        try:
            # Import here to avoid circular imports
            from microdrop_application.application import is_dark_mode
            
            theme = "dark" if is_dark_mode() else "light"
            # Set button styling with correct theme
            button_style = get_complete_stylesheet(theme, "default")
            self.capacitance_reset_button.setStyleSheet(button_style)
        except Exception as e:
            # Fallback to light theme if there's an error
            button_style = get_complete_stylesheet("light", "default")
            self.capacitance_reset_button.setStyleSheet(button_style)

    def update_theme_styling(self, theme="light"):
        """Update styling when theme changes."""
        button_style = get_complete_stylesheet(theme, "default")
        self.capacitance_reset_button.setStyleSheet(button_style)

    def update_capacitance_labels(self, event=None):
        self.liquid_capacitance_label.setText(f"C_l: {self.model.liquid_capacitance_over_area if self.model.liquid_capacitance_over_area is not None else '-'} pF") # TODO: Units are wrong, use pint to generate correct units
        self.filler_capacitance_label.setText(f"C_f: {self.model.filler_capacitance_over_area if self.model.filler_capacitance_over_area is not None else '-'} pF")

    def reset_capacitance(self):
        self.model.liquid_capacitance_over_area = None
        self.model.filler_capacitance_over_area = None
        