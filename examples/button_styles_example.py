"""
Example of how to use the new centralized button styles.
This demonstrates the benefits of the centralized approach.
"""

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton
import sys

# Import the centralized button styles
from microdrop_style.button_styles import (
    get_button_style, get_button_dimensions, 
    PRIMARY_BUTTON_STYLE
)

class ButtonStylesExample(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the example UI with different button types."""
        layout = QVBoxLayout()
        
        # Example 1: Using the helper function
        theme = "light"  # or "dark"
        
        # Get different button styles
        default_style = get_button_style(theme, "default")
        navigation_style = get_button_style(theme, "navigation")
        primary_style = get_button_style(theme, "primary")
        danger_style = get_button_style(theme, "danger")
        
        # Create buttons with different styles
        btn_default = QPushButton("Default Button")
        btn_default.setStyleSheet(default_style)
        
        btn_nav = QPushButton("Navigation")
        btn_nav.setStyleSheet(navigation_style)
        
        btn_primary = QPushButton("Primary Action")
        btn_primary.setStyleSheet(primary_style)
        
        btn_danger = QPushButton("Danger Action")
        btn_danger.setStyleSheet(danger_style)
        
        # Example 2: Using predefined styles directly
        btn_secondary = QPushButton("Secondary Action")
        btn_secondary.setStyleSheet(PRIMARY_BUTTON_STYLE)
        
        # Example 3: Getting button dimensions
        small_width, small_height = get_button_dimensions("small")
        btn_small = QPushButton("Small")
        btn_small.setFixedSize(small_width, small_height)
        btn_small.setStyleSheet(get_button_style(theme, "small"))
        
        # Add all buttons to layout
        layout.addWidget(btn_default)
        layout.addWidget(btn_nav)
        layout.addWidget(btn_primary)
        layout.addWidget(btn_danger)
        layout.addWidget(btn_secondary)
        layout.addWidget(btn_small)
        
        self.setLayout(layout)
        self.setWindowTitle("Button Styles Example")
        self.resize(300, 400)

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    window = QMainWindow()
    example_widget = ButtonStylesExample()
    window.setCentralWidget(example_widget)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
