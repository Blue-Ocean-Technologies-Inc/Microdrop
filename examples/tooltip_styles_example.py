"""
Example of how to use the new centralized tooltip styles.
This demonstrates consistent tooltip appearance across all components.
"""

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton
import sys

# Import the centralized tooltip styles
from microdrop_style.button_styles import get_tooltip_style

from microdrop_style.helpers import get_complete_stylesheet


class TooltipStylesExample(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the example UI with different tooltip styles."""
        layout = QVBoxLayout()
        
        # Example 1: Using just tooltip styles
        theme = "light"  # or "dark"
        tooltip_style = get_tooltip_style(theme)
        
        # Create buttons with different tooltip styles
        btn_basic = QPushButton("Basic Button")
        btn_basic.setToolTip("This is a basic button with consistent tooltip styling")
        btn_basic.setStyleSheet(tooltip_style)
        
        # Example 2: Using complete stylesheet (buttons + tooltips)
        complete_style = get_complete_stylesheet(theme, "default")
        btn_complete = QPushButton("Complete Styling")
        btn_complete.setToolTip("This button has both button and tooltip styles")
        btn_complete.setStyleSheet(complete_style)
        
        # Example 3: Using navigation button with tooltips
        nav_style = get_complete_stylesheet(theme, "navigation")
        btn_nav = QPushButton("→")
        btn_nav.setToolTip("Navigation button with consistent tooltip")
        btn_nav.setStyleSheet(nav_style)
        
        # Example 4: Using primary button with tooltips
        primary_style = get_complete_stylesheet(theme, "primary")
        btn_primary = QPushButton("Primary Action")
        btn_primary.setToolTip("Primary action button with consistent tooltip")
        btn_primary.setStyleSheet(primary_style)
        
        # Add all buttons to layout
        layout.addWidget(btn_basic)
        layout.addWidget(btn_complete)
        layout.addWidget(btn_nav)
        layout.addWidget(btn_primary)
        
        self.setLayout(layout)
        self.setWindowTitle("Tooltip Styles Example")
        self.resize(300, 300)

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    window = QMainWindow()
    example_widget = TooltipStylesExample()
    window.setCentralWidget(example_widget)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
