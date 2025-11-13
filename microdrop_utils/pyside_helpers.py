"""
PySide6 helper widgets and utilities for the Microdrop application.

This module provides reusable UI components that enhance the user interface
with consistent styling and behavior across the application.
"""

from typing import Union, List, Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QLabel, QPushButton, QApplication
from PySide6.QtCore import Qt


def horizontal_spacer_widget(width=10) -> QWidget:
    widget = QWidget()
    widget.setFixedWidth(width)
    return widget

class CollapsibleVStackBox(QWidget):
    """
    A minimalist, non-animated collapsible box that instantly
    hides or shows its content widget(s).
    
    This widget provides a clean way to organize UI elements into collapsible
    sections. It can contain either a single widget or multiple widgets stacked
    vertically. The box starts in an expanded state by default.
    
    Attributes:
        toggle_button (QToolButton): The clickable header button
        content_container (QWidget): Container holding all content widgets
        content_widgets (List[QWidget]): List of widgets contained in this box
    
    Args:
        title (str): The text displayed in the collapsible header
        control_widgets (Union[QWidget, List[QWidget], None]): Single widget or list of widgets to contain
        parent (Optional[QWidget]): Parent widget for this collapsible box
    
    Example:
        # Single widget
        label = QLabel("Some content")
        box = CollapsibleBox("Settings", control_widgets=label)
        
        # Multiple widgets
        widgets = [QLabel("Widget 1"), QPushButton("Button"), QLabel("Widget 2")]
        box = CollapsibleBox("Controls", control_widgets=widgets)
    """

    def __init__(self, title: str, control_widgets: Union[QWidget, List[QWidget], None],
                 parent: Optional[QWidget] = None) -> None:
        """
        Initialize the collapsible box with the given title and widgets.
        
        Args:
            title: The text displayed in the collapsible header
            control_widgets: Single widget or list of widgets to contain
            parent: Parent widget for this collapsible box
        """
        super(CollapsibleVStackBox, self).__init__(parent)

        # Main layout with zero margins or spacing
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # The clickable header
        self.toggle_button = QToolButton(self)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.setText(str(title))
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)  # Start Revealed
        self.toggle_button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")

        # Handle both single widget and multiple widgets
        self.content_widgets: List[QWidget] = []
        if control_widgets is not None:
            # Convert to list if single widget provided
            self.content_widgets = control_widgets if isinstance(control_widgets, list) else [control_widgets]

        # Create a container widget to hold all content widgets
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # Add all content widgets to the container
        for widget in self.content_widgets:
            if widget:
                widget.setVisible(True)  # Start Revealed
                try:
                    self.content_layout.addWidget(widget)
                except Exception as e:
                    print(e)

        # Connect the button's click to the toggle function
        self.toggle_button.toggled.connect(self._on_toggled)

        # Add widgets to the main layout
        self.main_layout.addWidget(self.toggle_button)
        self.main_layout.addWidget(self.content_container)

    def _on_toggled(self, checked: bool) -> None:
        """
        Handle the toggle button state change.
        
        Args:
            checked: True if the box should be expanded, False if collapsed
        """
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.content_container.setVisible(checked)

    def set_expanded(self, expanded: bool) -> None:
        """
        Programmatically set the expanded state of the collapsible box.
        
        Args:
            expanded: True to expand the box, False to collapse it
        """
        self.toggle_button.setChecked(expanded)

    def is_expanded(self) -> bool:
        """
        Check if the collapsible box is currently expanded.
        
        Returns:
            True if expanded, False if collapsed
        """
        return self.toggle_button.isChecked()


if __name__ == "__main__":
    def create_test_window() -> None:
        """
        Create a simple test window to demonstrate CollapsibleBox usage.
        
        This function creates a test application window with multiple collapsible
        boxes showing different use cases. It's useful for testing and as a
        reference for how to use the CollapsibleBox widget.
        """
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        # Create main window
        window = QWidget()
        window.setWindowTitle("CollapsibleBox Test")
        window.setGeometry(100, 100, 400, 600)
        
        # Create main layout
        layout = QVBoxLayout(window)
        
        # Example 1: Single widget
        single_widget = QLabel("This is a single widget inside a collapsible box.")
        single_widget.setStyleSheet("padding: 10px; background-color: #f0f0f0;")
        box1 = CollapsibleVStackBox("Single Widget Example", control_widgets=single_widget)
        
        # Example 2: Multiple widgets
        widgets = [
            QLabel("First widget in the list"),
            QPushButton("A button widget"),
            QLabel("Another label widget"),
            QPushButton("Another button")
        ]
        for widget in widgets:
            widget.setStyleSheet("padding: 5px; margin: 2px; background-color: #e0e0e0;")
        
        box2 = CollapsibleVStackBox("Multiple Widgets Example", control_widgets=widgets)
        
        # Example 3: Empty box (edge case)
        box3 = CollapsibleVStackBox("Empty Box", control_widgets=None)
        
        # Add boxes to layout
        layout.addWidget(box1)
        layout.addWidget(box2)
        layout.addWidget(box3)
        layout.addStretch()
        
        # Show window
        window.show()
        
        # Run the application
        app.exec()

    # Run the test when this file is executed directly
    create_test_window()


def get_qcolor_lighter_percent_from_factor(color: 'QColor', lightness_scale: float):
    """
    Calculates the integer percentage for QColor.lighter()
    based on a 0.0-1.0 scale.

    color: QColor
    lightness_scale: float (0.0 to 1.0)
        0.0 means same lightness as color (returns 100).
        1.0 means fully white (returns 100 / lightnessF).
    """

    # 1. Define the start of our scale (100% = no change)
    min_lightness_percent = 100.0

    current_lightness = color.lightness()

    # 2. Define the end of our scale (the factor to get to white)
    if current_lightness == 0:
        # Handle pure black:
        h, s, l, a = color.getHsl()
        color.setHsl(h, s, 1, a)

    # The factor needed to reach 1.0 lightness (white)
    # e.g., if lightnessF is 0.5 (gray), we need a factor of
    # 1.0 / 0.5 = 2.0, which is 200%.
    max_lightness_percent = int(255 * 100 / current_lightness)
    for n in range(max_lightness_percent, max_lightness_percent + 10000):
        if color.lighter(n).lightness() == 255:
            max_lightness_percent = n
            break

    # 3. Linearly interpolate between min and max
    lightness_percentage = min_lightness_percent + (max_lightness_percent - min_lightness_percent) * lightness_scale

    # QColor.lighter() expects an integer
    return int(lightness_percentage)
