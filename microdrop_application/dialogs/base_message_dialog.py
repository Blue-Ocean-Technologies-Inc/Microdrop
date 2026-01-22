"""
Base template class for custom messaging windows in Microdrop application.

This module provides the core BaseMessageDialog class that serves as a template
for all custom dialog types, ensuring consistent styling and behavior.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import winreg
except ImportError:
    winreg = None

from PySide6.QtCore import Qt, QPoint, QMimeData, QTimer, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from microdrop_style.colors import (
    PRIMARY_COLOR,
    ERROR_COLOR,
    WARNING_COLOR,
    SUCCESS_COLOR,
    INFO_COLOR,
    WHITE,
)
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_utils.font_helpers import load_font_family


class TriangleIconWidget(QWidget):
    """Custom widget to draw a triangle background for warning icons."""

    def __init__(
        self,
        icon_text: str,
        font: QFont,
        color: QColor,
        size: int = 64,
        text_y_offset: float = 0.6,
        parent=None,
    ):
        super().__init__(parent)
        self.icon_text = icon_text
        self.font = font
        self.color = color
        self.text_y_offset = text_y_offset
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Create triangle path based on your SVG path
        path = QPainterPath()
        width = self.width()
        height = self.height()

        # Scale factors to fit the SVG path (original: ~124x118)
        # to our widget size
        scale_x = width / 124.0
        scale_y = height / 118.0

        # Apply the SVG path coordinates with scaling
        # M 9.821,118.048
        path.moveTo(9.821 * scale_x, 118.048 * scale_y)

        # H 114.221 (horizontal line to x=114.221)
        path.lineTo(114.221 * scale_x, 118.048 * scale_y)

        # C 121.521,118.048 126.221,110.348 122.921,103.848 (cubic bezier)
        path.cubicTo(
            121.521 * scale_x,
            118.048 * scale_y,
            126.221 * scale_x,
            110.348 * scale_y,
            122.921 * scale_x,
            103.848 * scale_y,
        )

        # L 70.721,11.348 (line to)
        path.lineTo(70.721 * scale_x, 11.348 * scale_y)

        # C 67.12,4.149 56.821,4.149 53.221,11.348 (cubic bezier)
        path.cubicTo(
            67.12 * scale_x,
            4.149 * scale_y,
            56.821 * scale_x,
            4.149 * scale_y,
            53.221 * scale_x,
            11.348 * scale_y,
        )

        # L 1.021,103.848 (line to)
        path.lineTo(1.021 * scale_x, 103.848 * scale_y)

        # C -2.179,110.348 2.521,118.048 9.821,118.048 (cubic bezier)
        path.cubicTo(
            -2.179 * scale_x,
            110.348 * scale_y,
            2.521 * scale_x,
            118.048 * scale_y,
            9.821 * scale_x,
            118.048 * scale_y,
        )

        # Z (close path) - automatic with QPainterPath.closeSubpath()
        path.closeSubpath()

        # Fill the triangle
        painter.fillPath(path, self.color)

        # Draw the icon text - adjust position to center within triangle shape
        painter.setFont(self.font)
        painter.setPen(QColor("white"))

        # Calculate the visual center of the triangle
        # (not the widget rectangle)
        # Triangle's visual center is slightly lower than geometric center
        triangle_center_x = width / 2
        triangle_center_y = height * self.text_y_offset

        # Create a rectangle centered on the triangle's visual center
        text_rect = self.rect()
        text_rect.moveCenter(QPoint(int(triangle_center_x), int(triangle_center_y)))

        painter.drawText(text_rect, Qt.AlignCenter, self.icon_text)


class BaseMessageDialog(QDialog):
    """
    Base template class for custom messaging windows.

    This class provides a consistent foundation for all dialog types with:
    - Modern, styled appearance matching application theme
    - Icon and color scheme support for different message types
    - Flexible button configuration
    - Dark/light mode support
    - Customizable content areas
    """

    # Configuration constants
    ICON_FONT_SIZE = 36  # Size of the icon font in points
    DETAILS_VISIBLE_LINES = 4  # Visible lines in details before scrolling
    DETAILS_MAX_HEIGHT_RATIO = 0.6  # Max ratio of dialog height for details

    # Triangle icon configuration
    TRIANGLE_ICON_SIZE = 64  # Size of the triangle widget
    TRIANGLE_TEXT_Y_OFFSET = 0.6  # Vertical position of text within triangle

    # Color configuration - all colors used in dialogs
    LIGHT_ACCENT_FACTOR = 0.9  # How light to make the background accent
    DIALOG_BG_COLOR = "#FFFFFF"
    TEXT_COLOR = "#333333"
    BORDER_COLOR = "#E0E0E0"
    EXIT_BUTTON_COLOR = "#F5F5F5"
    EXIT_BUTTON_TEXT_COLOR = "#666666"
    COPY_BUTTON_COLOR = "#E8F4FD"
    COPY_BUTTON_HOVER_COLOR = "#D1E9FC"
    DETAILS_BG_COLOR = "rgba(255, 255, 255, 0.7)"

    # Signals
    button_clicked = Signal(str)  # Emits button text when clicked
    dialog_closed = Signal()  # Emits when dialog is closed

    # Dialog type constants
    TYPE_INFO = "info"
    TYPE_WARNING = "warning"
    TYPE_ERROR = "error"
    TYPE_SUCCESS = "success"
    TYPE_QUESTION = "question"

    # Custom result codes for different button types
    # Standard QDialog codes: Rejected = 0, Accepted = 1
    RESULT_CANCEL = 0  # Same as QDialog.Rejected
    RESULT_OK = 1  # Same as QDialog.Accepted
    RESULT_SAVE = 2  # Custom result for Save button
    RESULT_RESTART = 3  # Custom result for Restart button
    RESULT_CONTINUE = 4  # Custom result for Continue button
    RESULT_YES = 5  # Custom result for Yes button
    RESULT_NO = 6  # Custom result for No button
    RESULT_PAUSE = 7  # Custom result for Pause button
    RESULT_CUSTOM_1 = 10  # Custom result codes start from 10
    RESULT_CUSTOM_2 = 11
    RESULT_CUSTOM_3 = 12

    # Color mappings for dialog types
    TYPE_COLORS = {
        TYPE_INFO: INFO_COLOR,
        TYPE_WARNING: WARNING_COLOR,
        TYPE_ERROR: ERROR_COLOR,
        TYPE_SUCCESS: SUCCESS_COLOR,
        TYPE_QUESTION: PRIMARY_COLOR,
    }

    # Icon mappings for dialog types (using Google Material Icons)
    TYPE_ICONS = {
        TYPE_INFO: "info_i",  # info_i icon
        TYPE_WARNING: "priority_high",  # exclamation icon
        TYPE_ERROR: "report",  # exclamation icon
        TYPE_SUCCESS: "check",  # check icon
        TYPE_QUESTION: "question_mark",  # help icon (keeping as is)
    }

    # Class-level font caching for performance
    _text_font_family = None
    _icon_font_family = None
    _fonts_loaded = False

    def __init__(
        self,
        parent=None,
        title: str = "Message",
        message: str = "",
        dialog_type: str = TYPE_INFO,
        icon_path: Optional[str] = None,
        buttons: Optional[Dict[str, Any]] = None,
        modal: bool = True,
        resizable: bool = False,
        size: Optional[tuple] = None,
        disable_main_scrolling: bool = False,
    ):
        """
        Initialize the base message dialog.

        Args:
            parent: Parent widget
            title: Dialog window title
            message: Main message text to display
            dialog_type: Type of dialog (info, warning, error, success,
                         question)
            icon_path: Optional custom icon path
            buttons: Dict of button configurations
                     {text: {"action": callable, "style": str}}
            modal: Whether dialog should be modal
            resizable: Whether dialog can be resized
            size: Optional (width, height) tuple for fixed size
        """
        super().__init__(parent)

        self.dialog_type = dialog_type
        self.title_text = title
        self.message_text = message
        self.icon_path = icon_path
        self.button_configs = buttons or self._get_default_buttons()
        self.disable_main_scrolling = disable_main_scrolling

        # Check if HTML contains images - if so, make dialog resizable
        has_images = self._contains_html_image(self.message_text)
        self.is_resizable = resizable or has_images or disable_main_scrolling

        # Setup dialog properties
        self.setModal(modal)
        self.setWindowTitle(title)

        # Set size constraints
        # If HTML contains images, make dialog resizable to accommodate them
        # Calculate minimum dialog size:
        # Header (140px) + Content (100px) + Buttons (~60px) = ~300px minimum
        min_dialog_height = 300
        min_dialog_width = 400

        if size:
            if has_images:
                min_size = QSize(max(size[0], min_dialog_width), max(size[1], min_dialog_height))
                self.setMinimumSize(min_size)
                self.setMaximumSize(QSize(900, 700))
            else:
                min_size = QSize(max(size[0], min_dialog_width), max(size[1], min_dialog_height))
                self.setFixedSize(min_size)
        else:
            self.setMinimumSize(QSize(min_dialog_width, min_dialog_height))
            if not self.is_resizable:
                self.setMaximumSize(QSize(900, 700))
            elif has_images:
                self.setMaximumSize(QSize(1000, 800))
            else:
                self.setMaximumSize(QSize(1000, 800))

        # Setup UI
        self._setup_fonts()
        self._setup_ui()
        self._apply_styling()
        self._connect_signals()
        QTimer.singleShot(0, self._adjust_min_size_to_message)

        # Position dialog
        self._center_on_parent()
        self._base_min_size = self.minimumSize()

    @staticmethod
    def _contains_html_image(text: str) -> bool:
        """Check if HTML content contains image tags."""
        # Check for <img> tags (case insensitive)
        img_pattern = r"<img[^>]*>"
        return bool(re.search(img_pattern, text, re.IGNORECASE))

    def _adjust_min_size_to_message(self):
        """Adjust dialog minimum size to fit the core message text."""
        if not hasattr(self, "message_label"):
            return
        if self._should_use_scrolling():
            return
        if not self.message_text:
            return

        content_width = self.message_label.width()
        if content_width <= 0 and hasattr(self, "content_frame"):
            content_width = self.content_frame.width() - 50
        if content_width <= 0:
            content_width = 500
        content_width = max(200, content_width)

        doc = QTextDocument()
        doc.setDefaultFont(self.message_label.font())
        if self.message_label.textFormat() == Qt.TextFormat.RichText:
            doc.setHtml(self.message_text)
        else:
            doc.setPlainText(self.message_text)
        doc.setTextWidth(content_width)

        message_height = int(doc.size().height()) + 2
        self.message_label.setMinimumHeight(message_height)
        self.adjustSize()
        self.setMinimumSize(
            max(self.minimumWidth(), self.width()),
            max(self.minimumHeight(), self.height()),
        )
        self._center_on_parent()

    def _should_use_scrolling(self) -> bool:
        """
        Determine if the dialog should use scrolling based on content length.

        If HTML content contains images, prefer resizing the dialog instead
        of using scrolling.
        """
        if self.disable_main_scrolling:
            return False

        # Check if message contains HTML images
        if self._contains_html_image(self.message_text):
            return False

        # Use scrolling if:
        # 1. Message is very long (>500 characters)
        # 2. Message has many lines (>8 lines)
        # 3. Dialog has a fixed size that might not accommodate content
        message_length = len(self.message_text)
        line_count = self.message_text.count("\n") + 1

        # Check if content is likely to be too long
        if message_length > 500 or line_count > 8:
            return True

        # Check if dialog has a fixed small size
        current_size = self.size()
        if current_size.isValid():
            height = current_size.height()
            if height <= 400 and (message_length > 200 or line_count > 4):
                return True

        return False

    def _setup_fonts(self):
        """Setup font families for the dialog with caching for performance."""
        # Only load fonts once for all dialog instances
        if not self._fonts_loaded:
            # Load Inter font for text
            inter_font_path = Path(__file__).parent.parent.parent / "microdrop_style" / "fonts" / "Inter-VariableFont_opsz,wght.ttf"
            self._text_font_family = load_font_family(inter_font_path) or "Inter"

            # Load Material Symbols for icons
            icon_font_path = (
                Path(__file__).parent.parent.parent
                / "microdrop_style"
                / "icons"
                / "Material_Symbols_Outlined"
                / "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf"
            )
            self._icon_font_family = load_font_family(icon_font_path) or ICON_FONT_FAMILY

            self._fonts_loaded = True

        # Use cached fonts
        self.text_font_family = self._text_font_family
        self.icon_font_family = self._icon_font_family

    def _setup_ui(self):
        """Setup the user interface components."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Header frame
        self._create_header()

        # Content frame
        self._create_content()

        # Button frame
        self._create_buttons()

        self.setLayout(self.main_layout)

    def _create_header(self):
        """Create the header section with centered icon and title."""
        self.header_frame = QFrame()
        self.header_frame.setObjectName("headerFrame")
        header_layout = QVBoxLayout(self.header_frame)
        header_layout.setContentsMargins(20, 0, 20, 20)
        header_layout.setSpacing(1)
        header_layout.setAlignment(Qt.AlignTop)

        self.header_frame.setFixedHeight(140)
        self.header_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Close button in top right corner
        close_layout = QHBoxLayout()
        close_layout.setContentsMargins(0, 0, 0, 1)
        close_layout.addStretch()
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(20, 20)
        close_font = QFont(self.text_font_family)
        close_font.setPointSize(14)
        close_font.setWeight(QFont.Weight.Bold)
        self.close_button.setFont(close_font)
        self.close_button.clicked.connect(self.reject)
        close_layout.addWidget(self.close_button)
        header_layout.addLayout(close_layout)

        # Icon - centered with custom shapes for different types
        if self.dialog_type == self.TYPE_WARNING:
            # Use custom triangle widget for warnings
            icon_text = self.TYPE_ICONS.get(self.dialog_type, self.TYPE_ICONS[self.TYPE_INFO])
            icon_font = QFont(self.icon_font_family)
            icon_font.setPointSize(self.ICON_FONT_SIZE)
            dialog_color = QColor(self.TYPE_COLORS.get(self.dialog_type, WARNING_COLOR))
            self.icon_widget = TriangleIconWidget(
                icon_text,
                icon_font,
                dialog_color,
                size=self.TRIANGLE_ICON_SIZE,
                text_y_offset=self.TRIANGLE_TEXT_Y_OFFSET,
            )
            header_layout.addWidget(self.icon_widget, 0, Qt.AlignCenter)
        else:
            # Use regular label for other types
            self.icon_label = QLabel()
            self.icon_label.setObjectName("iconLabel")
            if self.icon_path and Path(self.icon_path).exists():
                # Custom icon from file
                pixmap = QPixmap(self.icon_path)
                scaled_pixmap = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(scaled_pixmap)
            else:
                # Material icon
                icon_text = self.TYPE_ICONS.get(self.dialog_type, self.TYPE_ICONS[self.TYPE_INFO])
                self.icon_label.setText(icon_text)
                icon_font = QFont(self.icon_font_family)
                icon_font.setPointSize(self.ICON_FONT_SIZE)
                self.icon_label.setFont(icon_font)

            self.icon_label.setFixedSize(64, 64)
            self.icon_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(self.icon_label, 0, Qt.AlignCenter)

        # Title - centered below icon
        self.title_label = QLabel(self.title_text)
        self.title_label.setObjectName("titleLabel")
        title_font = QFont(self.text_font_family)
        title_font.setPointSize(18)
        title_font.setWeight(QFont.Weight.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.title_label, 0, Qt.AlignCenter)

        self.main_layout.addWidget(self.header_frame)

    def _get_scroll_area_style(self) -> str:
        """Get the stylesheet for the scroll area."""
        return f"""
            QScrollArea {{
                background-color: {self.DIALOG_BG_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 4px;
            }}
            QScrollArea QWidget {{
                background-color: {self.DIALOG_BG_COLOR};
            }}
            QScrollBar:vertical {{
                background-color: #F0F0F0;
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: #C0C0C0;
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: #A0A0A0;
            }}
            QScrollBar:horizontal {{
                background-color: #F0F0F0;
                height: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: #C0C0C0;
                border-radius: 6px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: #A0A0A0;
            }}
        """

    def _create_message_label(self, text: str) -> QLabel:
        """Create and configure the message label."""
        label = QLabel(text)
        label.setObjectName("messageLabel")
        message_font = QFont(self.text_font_family)
        message_font.setPointSize(12)
        label.setFont(message_font)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        label.setOpenExternalLinks(True)

        if self._contains_html_image(text):
            label.setTextFormat(Qt.TextFormat.RichText)

        return label

    def _create_content(self):
        """Create the content area with message text."""
        self.content_frame = QFrame()
        self.content_frame.setObjectName("contentFrame")
        self.content_frame.setMinimumHeight(100)
        self.content_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(25, 0, 25, 25)
        content_layout.setSpacing(15)

        # Check if we need scrolling for long content
        needs_scrolling = self._should_use_scrolling()

        # Common message label creation
        self.message_label = self._create_message_label(self.message_text)

        if needs_scrolling:
            # Create scroll area for long content
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

            # Set consistent styling regardless of dark/light mode
            scroll_area.setStyleSheet(self._get_scroll_area_style())

            # Create widget to hold scrollable content
            scroll_widget = QWidget()
            scroll_widget.setStyleSheet(f"background-color: {self.DIALOG_BG_COLOR};")
            scroll_layout = QVBoxLayout(scroll_widget)
            scroll_layout.setContentsMargins(0, 0, 0, 0)
            scroll_layout.setSpacing(15)

            scroll_layout.addWidget(self.message_label)

            # Additional content area for subclasses
            self.additional_content_layout = QVBoxLayout()
            scroll_layout.addLayout(self.additional_content_layout)

            scroll_area.setWidget(scroll_widget)
            content_layout.addWidget(scroll_area)
        else:
            # Standard layout for shorter content - support HTML if needed
            if self._contains_html_image(self.message_text):
                self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            else:
                self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            content_layout.addWidget(self.message_label)

            # Additional content area for subclasses
            self.additional_content_layout = QVBoxLayout()
            content_layout.addLayout(self.additional_content_layout)

        self.main_layout.addWidget(self.content_frame, 1)

    def _button_sort_key(self, item):
        """
        Sort key for buttons to ensure exit/cancel buttons come first (left).
        """
        button_text, _ = item
        # Exit/cancel buttons get priority 0 (leftmost)
        lower_text = button_text.lower()
        if lower_text in ["exit", "cancel", "close", "no", "nope"] or "discard" in lower_text or "continue anyway" in lower_text:
            return 0
        # All other buttons get priority 1 (rightward)
        return 1

    def _create_buttons(self):
        """Create the button section."""
        self.button_frame = QFrame()
        self.button_frame.setObjectName("buttonFrame")
        button_layout = QHBoxLayout(self.button_frame)
        button_layout.setContentsMargins(20, 15, 20, 20)
        button_layout.setSpacing(12)

        # Calculate button width to take up about 35% of window width each
        # Assuming minimum dialog width of 400px, 35% would be about 140px each
        button_width = 140
        button_height = 32  # Slightly shorter

        # Add stretch to center buttons
        button_layout.addStretch()

        self.buttons = {}
        button_list = list(self.button_configs.items())

        # Sort buttons to ensure exit/cancel buttons come first (left side)
        button_list.sort(key=self._button_sort_key)

        for i, (button_text, config) in enumerate(button_list):
            button = QPushButton(button_text)
            # Set proper object name for styling - Exit buttons get special
            # styling
            if self._button_sort_key((button_text, None)) == 0:
                button.setObjectName("exitButton")
            else:
                button.setObjectName(f"{button_text.lower().replace(' ', '')}Button")

            # Button font
            button_font = QFont(self.text_font_family)
            button_font.setPointSize(12)
            button_font.setWeight(QFont.Weight.Medium)
            button.setFont(button_font)

            # Button size - wider and centered
            button.setFixedSize(button_width, button_height)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            # Connect button action
            if "action" in config and callable(config["action"]):
                button.clicked.connect(lambda checked, action=config["action"]: action())

            # Emit signal when clicked
            button.clicked.connect(lambda checked, text=button_text: self.button_clicked.emit(text))

            self.buttons[button_text] = button
            button_layout.addWidget(button)

        # Add stretch to center buttons
        button_layout.addStretch()

        self.main_layout.addWidget(self.button_frame)

    def _apply_styling(self):
        """Apply consistent styling based on dialog type."""
        dialog_color = self.TYPE_COLORS.get(self.dialog_type, INFO_COLOR)

        # Create light accent background based on theme color
        light_accent_bg = self._lighten_color(dialog_color, self.LIGHT_ACCENT_FACTOR)

        # Dialog styling with themed light background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {light_accent_bg};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 12px;
            }}

            QFrame#headerFrame {{
                background-color: {light_accent_bg};
                border: none;
            }}

            QLabel#iconLabel {{
                color: {WHITE};
                background-color: {dialog_color};
                {self._get_icon_shape_style()};
                padding: 0px;
            }}

            QLabel#titleLabel {{
                color: {dialog_color};
                background: transparent;
                font-weight: 700;
            }}

            QPushButton#closeButton {{
                background: transparent;
                border: none;
                color: {self.TEXT_COLOR};
                border-radius: 16px;
                font-weight: bold;
            }}

            QPushButton#closeButton:hover {{
                background-color: rgba(0, 0, 0, 0.1);
            }}

            QFrame#contentFrame {{
                background-color: {light_accent_bg};
                border: none;
            }}

            QLabel#messageLabel {{
                color: {self.TEXT_COLOR};
                background: transparent;
                line-height: 1.5;
            }}

            QFrame#buttonFrame {{
                background-color: {light_accent_bg};
                border: none;
                border-top: 1px solid {self.BORDER_COLOR};
            }}

            QPushButton {{
                background-color: {dialog_color};
                color: {WHITE};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
                font-size: 12px;
            }}

            QPushButton:hover {{
                background-color: {self._darken_color(dialog_color, 0.1)};
            }}

            QPushButton:pressed {{
                background-color: {self._darken_color(dialog_color, 0.2)};
            }}

            QPushButton#exitButton {{
                background-color: {self.EXIT_BUTTON_COLOR};
                color: {self.EXIT_BUTTON_TEXT_COLOR};
                border: 1px solid {self.BORDER_COLOR};
            }}

            QPushButton#exitButton:hover {{
                background-color: {self._darken_color(
                    self.EXIT_BUTTON_COLOR, 0.05
                )};
                border-color: {self._darken_color(self.BORDER_COLOR, 0.1)};
            }}

            QPushButton#exitButton:pressed {{
                background-color: {self._darken_color(
                    self.EXIT_BUTTON_COLOR, 0.1
                )};
            }}

            QPushButton#copyButton {{
                background-color: {self.COPY_BUTTON_COLOR};
                color: {self.TEXT_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                max-width: 80px;
            }}

            QPushButton#copyButton:hover {{
                background-color: {self.COPY_BUTTON_HOVER_COLOR};
            }}

            QTextBrowser {{
                background-color: {self.DETAILS_BG_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 6px;
                padding: 8px;
                font-family: monospace;
                font-size: 11px;
                color: {self.TEXT_COLOR};
            }}
        """)

        # Add subtle drop shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

    def _get_default_buttons(self) -> Dict[str, Any]:
        """Get default button configuration based on dialog type."""
        if self.dialog_type == self.TYPE_QUESTION:
            return {"Exit": {"action": self.reject}, "Save": {"action": self.accept}}
        else:
            return {"Exit": {"action": self.reject}, "OK": {"action": self.accept}}

    def _connect_signals(self):
        """Connect internal signals."""
        self.finished.connect(lambda: self.dialog_closed.emit())

    def _center_on_parent(self):
        """Center the dialog on its parent or screen."""
        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
        else:
            # Center on screen
            screen = self.screen().availableGeometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            self.move(x, y)

    def _is_dark_mode(self) -> bool:
        """Check if the application is in dark mode."""
        try:
            # Simple check based on palette - can be enhanced
            palette = self.palette()
            bg_color = palette.color(palette.ColorRole.Window)
            return bg_color.lightness() < 128
        except (AttributeError, Exception):
            # Fallback to system-level dark mode detection
            return self._detect_system_dark_mode()

    def _detect_system_dark_mode(self) -> bool:
        """Detect system-level dark mode as fallback."""
        if sys.platform == "darwin":
            try:
                mode = subprocess.check_output("defaults read -g AppleInterfaceStyle", shell=True).strip()
                return mode == b"Dark"
            except Exception:
                return False
        elif sys.platform.startswith("win"):
            if winreg is None:
                return False
            try:
                reg = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                key = winreg.OpenKey(reg, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                apps_use_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return apps_use_light_theme == 0
            except Exception:
                return False
        else:
            # Linux/other Unix systems
            gtk_theme = os.environ.get("GTK_THEME", "").lower()
            if "dark" in gtk_theme:
                return True
            qt_theme = os.environ.get("QT_QPA_PLATFORMTHEME", "").lower()
            if "dark" in qt_theme:
                return True
            return False

    def _darken_color(self, color_hex: str, factor: float) -> str:
        """Darken a hex color by a factor."""
        try:
            color = QColor(color_hex)
            h, s, lightness, a = color.getHsl()
            lightness = max(0, int(lightness * (1 - factor)))
            new_color = QColor.fromHsl(h, s, lightness, a)
            return new_color.name()
        except Exception:
            return color_hex

    def _lighten_color(self, color_hex: str, factor: float) -> str:
        """Lighten a hex color by a factor (0.0 = no change, 1.0 = white)."""
        try:
            color = QColor(color_hex)
            r, g, b, a = color.getRgb()

            # Lighten by interpolating towards white
            r = int(r + (255 - r) * factor)
            g = int(g + (255 - g) * factor)
            b = int(b + (255 - b) * factor)

            new_color = QColor(r, g, b, a)
            return new_color.name()
        except Exception:
            return "#F8F9FA"  # Fallback light gray

    def _get_icon_shape_style(self) -> str:
        """
        Get the appropriate shape styling for the icon based on dialog type.
        """
        if self.dialog_type == self.TYPE_SUCCESS:
            # Rounded square for success
            return "border-radius: 8px"
        elif self.dialog_type == self.TYPE_WARNING:
            # Create triangle effect using clip-path equivalent
            # Since CSS clip-path isn't well supported in Qt, we'll use a
            # more rounded shape
            return "border-radius: 12px 12px 32px 12px"
        else:
            # Circle for info, error, and question
            return "border-radius: 32px"

    # Public methods for customization
    def set_message(self, message: str, is_html: bool = False):
        """Update the message text."""
        self.message_text = message
        if hasattr(self, "message_label"):
            if is_html:
                self.message_label.setTextFormat(Qt.TextFormat.RichText)
                self.message_label.setText(message)
            else:
                self.message_label.setTextFormat(Qt.TextFormat.PlainText)
                self.message_label.setText(message)

    def set_title(self, title: str):
        """Update the dialog title."""
        self.title_text = title
        self.setWindowTitle(title)
        if hasattr(self, "title_label"):
            self.title_label.setText(title)

    def add_content_widget(self, widget):
        """Add additional widget to content area."""
        if hasattr(self, "additional_content_layout"):
            self.additional_content_layout.addWidget(widget)

    def _create_details_header(self, details_label: str, collapsible: bool) -> QHBoxLayout:
        """Create the header for the details section."""
        header_layout = QHBoxLayout()

        # Details label
        label = QLabel(details_label)
        label_font = QFont(self.text_font_family)
        label_font.setPointSize(12)
        label_font.setWeight(QFont.Weight.Bold)
        label.setFont(label_font)
        label.setStyleSheet(f"color: {self.TEXT_COLOR};")
        header_layout.addWidget(label)

        header_layout.addStretch()

        # Show/Hide Details button (if collapsible)
        self.details_visible = not collapsible
        if collapsible:
            self.show_details_button = QPushButton("Show Details")
            self.show_details_button.setObjectName("showDetailsButton")
            show_details_font = QFont(self.text_font_family)
            show_details_font.setPointSize(10)
            self.show_details_button.setFont(show_details_font)
            self.show_details_button.setStyleSheet(
                f"QPushButton {{ color: {PRIMARY_COLOR}; border: none; " f"background: transparent; text-decoration: underline; }}"
            )
            header_layout.addWidget(self.show_details_button)

        return header_layout

    def _create_copy_button(self) -> QPushButton:
        """Create the copy button."""
        copy_button = QPushButton("content_copy")
        copy_button.setObjectName("copyButton")
        copy_button.setToolTip("Copy to clipboard")
        copy_button.setFixedSize(60, 24)

        # Set material icon font
        copy_font = QFont(self.icon_font_family)
        copy_font.setPointSize(12)
        copy_button.setFont(copy_font)

        return copy_button

    def _create_details_browser(self, details_text: str, visible_lines: Optional[int]) -> QTextBrowser:
        """Create and configure the details text browser."""
        details_browser = QTextBrowser()
        details_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        details_font = QFont(self.text_font_family, 11)
        details_browser.setFont(details_font)
        line_height = details_browser.fontMetrics().lineSpacing()
        lines_to_show = visible_lines if visible_lines else self.DETAILS_VISIBLE_LINES
        details_height = (line_height * lines_to_show) + 16
        details_browser.setMinimumHeight(details_height)

        # Convert markdown-like formatting to HTML for better display
        html_text = details_text.replace("**", "<b>", 1).replace("**", "</b>", 1)
        html_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", html_text)
        html_text = html_text.replace("\n", "<br>")

        # Better styling for tracebacks and code
        formatted_html = f"""<div style='font-family: "{self.text_font_family}";
            font-size: 11px; line-height: 1.4; white-space: pre-wrap;
            color: #2d2d2d;'>{html_text}</div>"""
        details_browser.setHtml(formatted_html)

        # Store reference for copy functionality
        self.details_formatted_html = formatted_html

        return details_browser

    def add_details_with_copy(
        self,
        details_text: str,
        details_label: str = "Details:",
        collapsible: bool = True,
        visible_lines: Optional[int] = None,
    ):
        """
        Add a details section with copy to clipboard functionality.
        """
        # Container for the entire details section
        details_container = QFrame()
        container_layout = QVBoxLayout(details_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(5)

        # Header with label, show/hide button, and copy button
        header_layout = self._create_details_header(details_label, collapsible)
        copy_button = self._create_copy_button()
        header_layout.addWidget(copy_button)
        container_layout.addLayout(header_layout)

        # Text browser for details
        details_browser = self._create_details_browser(details_text, visible_lines)
        self.details_browser = details_browser

        # Connect copy button
        copy_button.clicked.connect(lambda: self._copy_formatted_to_clipboard(self.details_formatted_html, details_text))

        # Add details browser to container
        container_layout.addWidget(details_browser)

        # Set initial visibility and connect toggle
        if collapsible:
            details_browser.setVisible(False)
            self.show_details_button.clicked.connect(self._toggle_details_visibility)
        else:
            details_browser.setVisible(True)

        self.add_content_widget(details_container)
        self.adjustSize()
        self._base_min_size = self.minimumSize()
        return details_browser, copy_button

    def _toggle_details_visibility(self):
        """Toggle the visibility of the details section."""
        if hasattr(self, "details_browser") and hasattr(self, "show_details_button"):
            self.details_visible = not self.details_visible
            self.details_browser.setVisible(self.details_visible)

            if self.details_visible:
                self.show_details_button.setText("Hide Details")
                self.adjustSize()
                self._update_details_max_height()
                max_width = self.maximumWidth()
                max_height = self.maximumHeight()
                desired_width = self.width()
                desired_height = self.height()
                if max_width > 0:
                    desired_width = min(desired_width, max_width)
                if max_height > 0:
                    desired_height = min(desired_height, max_height)

                min_width = max(self._base_min_size.width(), desired_width)
                min_height = max(self._base_min_size.height(), desired_height)
                if max_width > 0:
                    min_width = min(min_width, max_width)
                if max_height > 0:
                    min_height = min(min_height, max_height)

                self.setMinimumSize(min_width, min_height)
            else:
                self.show_details_button.setText("Show Details")
                self.setMinimumSize(self._base_min_size)
                self.adjustSize()
            self._center_on_parent()

    def _update_details_max_height(self):
        """Cap details height based on dialog size."""
        if not hasattr(self, "details_browser"):
            return
        if not self.details_browser.isVisible():
            return
        base_height = self.height()
        if hasattr(self, "content_frame"):
            base_height = self.content_frame.height()
        max_height = int(base_height * self.DETAILS_MAX_HEIGHT_RATIO)
        if max_height > 0:
            self.details_browser.setMaximumHeight(max_height)

    def resizeEvent(self, event):
        """Keep details height capped during resize."""
        super().resizeEvent(event)
        self._update_details_max_height()

    def _copy_to_clipboard(self, text: str):
        """Copy text to system clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        print(f"Copied to clipboard: {len(text)} characters")

    def _copy_formatted_to_clipboard(self, formatted_html: str, plain_text: str):
        """
        Copy formatted HTML text to clipboard.

        Uses MIME data to support both HTML and plain text formats,
        allowing applications to choose the format they support.
        """
        clipboard = QApplication.clipboard()
        mime_data = QMimeData()

        mime_data.setHtml(formatted_html)
        mime_data.setText(plain_text)

        clipboard.setMimeData(mime_data)
        print(f"Copied formatted text to clipboard: {len(plain_text)} characters")

    def get_button(self, button_text: str) -> Optional[QPushButton]:
        """Get button by text."""
        return self.buttons.get(button_text)

    def set_button_text(self, old_text: str, new_text: str):
        """Change button text after creation."""
        if old_text in self.buttons:
            button = self.buttons[old_text]
            button.setText(new_text)
            # Update the dictionary key
            self.buttons[new_text] = self.buttons.pop(old_text)
            # Update object name for styling - preserve exit button styling
            lower_text = new_text.lower()
            if lower_text in ["exit", "cancel", "close", "no", "nope"] or "discard" in lower_text or "continue anyway" in lower_text:
                button.setObjectName("exitButton")
            else:
                button.setObjectName(f"{new_text.lower().replace(' ', '')}Button")

    def show_dialog(self) -> int:
        """Show the dialog and return the result."""
        return self.exec()

    def close_with_result(self, result_code: int):
        """
        Close the dialog with a specific result code.

        Args:
            result_code: The result code to return (use RESULT_* constants)
        """
        self.done(result_code)

    # Class method for quick dialog creation
    @classmethod
    def show_message(
        cls,
        parent=None,
        title: str = "Message",
        message: str = "",
        dialog_type: str = TYPE_INFO,
        **kwargs,
    ) -> int:
        """
        Convenience method to show a simple message dialog.

        Returns:
            Dialog result code (QDialog.Accepted or QDialog.Rejected)
        """
        dialog = cls(
            parent=parent,
            title=title,
            message=message,
            dialog_type=dialog_type,
            **kwargs,
        )
        return dialog.show_dialog()
