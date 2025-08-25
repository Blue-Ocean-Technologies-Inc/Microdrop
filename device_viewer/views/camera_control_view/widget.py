from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QSizePolicy

from microdrop_style.button_styles import get_complete_stylesheet


class CameraControlWidget(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model

        # Apply theme-aware styling
        self._apply_theme_styling()

        # Make checkable buttons
        self.button_align = QPushButton("view_in_ar")
        self.button_align.setToolTip("Align Camera")

        self.button_reset = QPushButton("frame_reload")
        self.button_reset.setToolTip("Reset Camera")

        # btn_layout
        btn_layout = QHBoxLayout()
        for btn in [self.button_align]:
            btn.setCheckable(True)
            btn_layout.addWidget(btn)
        btn_layout.addWidget(self.button_reset)
        btn_layout.addStretch()  # Add stretch to push buttons to the left and expand the layout
        
        # Main layout
        layout = QVBoxLayout()
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
        # Set size policy to allow horizontal expansion but keep natural height
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.sync_buttons_and_label()

        self.button_align.clicked.connect(lambda: self.set_mode("camera-place"))
        self.button_reset.clicked.connect(self.reset)
        self.model.observe(self.on_mode_changed, "mode")

    def _apply_theme_styling(self):
        """Apply theme-aware styling to the widget."""
        try:
            # Import here to avoid circular imports
            from microdrop_application.application import is_dark_mode
            
            theme = "dark" if is_dark_mode() else "light"
            # Use complete stylesheet with tooltips for icon buttons
            icon_button_style = get_complete_stylesheet(theme, "default")
            self.setStyleSheet(icon_button_style)
        except Exception as e:
            # Fallback to light theme if there's an error
            icon_button_style = get_complete_stylesheet("light", "default")
            self.setStyleSheet(icon_button_style)

    def update_theme_styling(self, theme="light"):
        """Update styling when theme changes."""
        icon_button_style = get_complete_stylesheet(theme, "default")
        self.setStyleSheet(icon_button_style)

    def on_mode_changed(self, event):
        self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        self.button_align.setChecked(self.model.mode == "camera-place")

    def set_mode(self, mode):
        self.model.mode = mode

    def reset(self):
        """Reset the camera control widget to its initial state."""
        self.model.camera_perspective.reset()
        if self.model.mode == "camera-edit":
            # Reset to camera-place mode after reset
            self.model.mode = "camera-place"