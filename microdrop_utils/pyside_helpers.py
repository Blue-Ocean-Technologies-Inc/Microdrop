from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton
from PySide6.QtCore import Qt


class CollapsibleBox(QWidget):
    """
    A minimalist, non-animated collapsible box that instantly
    hides or shows its content widget.
    """

    def __init__(self, title, content_widget, parent=None):
        super(CollapsibleBox, self).__init__(parent)

        # Main layout with zero margins or spacing
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # The clickable header
        self.toggle_button = QToolButton(self)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.RightArrow)
        self.toggle_button.setText(str(title))
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)  # Start collapsed
        self.toggle_button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")

        # Set the content widget directly
        self.content_widget = content_widget
        if self.content_widget:
            self.content_widget.setVisible(False)  # Start hidden

        # Connect the button's click to the toggle function
        self.toggle_button.toggled.connect(self._on_toggled)

        # Add widgets to the layout
        self.main_layout.addWidget(self.toggle_button)
        if self.content_widget:
            self.main_layout.addWidget(self.content_widget)

    def _on_toggled(self, checked):
        """Instantly shows or hides the content."""
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        if self.content_widget:
            self.content_widget.setVisible(checked)