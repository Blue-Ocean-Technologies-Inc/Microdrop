"""
Base template class for custom messaging windows in Microdrop application.

This module provides the core BaseMessageDialog class that serves as a template
for all custom dialog types, ensuring consistent styling and behavior.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QSizePolicy, QGraphicsDropShadowEffect, QWidget, QApplication,
    QTextBrowser
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QPixmap, QColor, QPainter, QPainterPath

from microdrop_style.colors import (
    PRIMARY_COLOR, ERROR_COLOR, WARNING_COLOR,
    SUCCESS_COLOR, INFO_COLOR, WHITE, BLACK, GREY
)
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_utils.font_helpers import load_font_family


class TriangleIconWidget(QWidget):
    """Custom widget to draw a triangle background for warning icons."""
    
    def __init__(self, icon_text: str, font: QFont, color: QColor, size: int = 64, text_y_offset: float = 0.6, parent=None):
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
        
        # Scale factors to fit the SVG path (original: ~124x118) to our widget size
        scale_x = width / 124.0
        scale_y = height / 118.0
        
        # Apply the SVG path coordinates with scaling
        # M 9.821,118.048
        path.moveTo(9.821 * scale_x, 118.048 * scale_y)
        
        # H 114.221 (horizontal line to x=114.221)
        path.lineTo(114.221 * scale_x, 118.048 * scale_y)
        
        # C 121.521,118.048 126.221,110.348 122.921,103.848 (cubic bezier curve)
        path.cubicTo(121.521 * scale_x, 118.048 * scale_y,
                     126.221 * scale_x, 110.348 * scale_y,
                     122.921 * scale_x, 103.848 * scale_y)
        
        # L 70.721,11.348 (line to)
        path.lineTo(70.721 * scale_x, 11.348 * scale_y)
        
        # C 67.12,4.149 56.821,4.149 53.221,11.348 (cubic bezier curve)
        path.cubicTo(67.12 * scale_x, 4.149 * scale_y,
                     56.821 * scale_x, 4.149 * scale_y,
                     53.221 * scale_x, 11.348 * scale_y)
        
        # L 1.021,103.848 (line to)
        path.lineTo(1.021 * scale_x, 103.848 * scale_y)
        
        # C -2.179,110.348 2.521,118.048 9.821,118.048 (cubic bezier curve)
        path.cubicTo(-2.179 * scale_x, 110.348 * scale_y,
                     2.521 * scale_x, 118.048 * scale_y,
                     9.821 * scale_x, 118.048 * scale_y)
        
        # Z (close path) - automatic with QPainterPath.closeSubpath()
        path.closeSubpath()
        
        # Fill the triangle
        painter.fillPath(path, self.color)
        
        # Draw the icon text - adjust position to center within triangle shape
        painter.setFont(self.font)
        painter.setPen(QColor("white"))
        
        # Calculate the visual center of the triangle (not the widget rectangle)
        # Triangle's visual center is slightly lower than geometric center
        triangle_center_x = width / 2
        triangle_center_y = height * self.text_y_offset  # Configurable vertical position
        
        # Create a rectangle centered on the triangle's visual center
        from PySide6.QtCore import QPoint
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
    
    # Triangle icon configuration
    TRIANGLE_ICON_SIZE = 64  # Size of the triangle widget (width and height)
    TRIANGLE_TEXT_Y_OFFSET = 0.6  # Vertical position of text within triangle (0.0 = top, 1.0 = bottom)
    
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
    dialog_closed = Signal()      # Emits when dialog is closed
    
    # Dialog type constants
    TYPE_INFO = "info"
    TYPE_WARNING = "warning"
    TYPE_ERROR = "error"
    TYPE_SUCCESS = "success"
    TYPE_QUESTION = "question"
    
    # Custom result codes for different button types
    # Standard QDialog codes: Rejected = 0, Accepted = 1
    RESULT_CANCEL = 0      # Same as QDialog.Rejected
    RESULT_OK = 1          # Same as QDialog.Accepted  
    RESULT_SAVE = 2        # Custom result for Save button
    RESULT_RESTART = 3     # Custom result for Restart button
    RESULT_CONTINUE = 4    # Custom result for Continue button
    RESULT_YES = 5         # Custom result for Yes button
    RESULT_NO = 6          # Custom result for No button
    RESULT_PAUSE = 7       # Custom result for Pause button
    RESULT_CUSTOM_1 = 10   # Custom result codes start from 10
    RESULT_CUSTOM_2 = 11
    RESULT_CUSTOM_3 = 12
    
    # Color mappings for dialog types
    TYPE_COLORS = {
        TYPE_INFO: INFO_COLOR,
        TYPE_WARNING: WARNING_COLOR,
        TYPE_ERROR: ERROR_COLOR,
        TYPE_SUCCESS: SUCCESS_COLOR,
        TYPE_QUESTION: PRIMARY_COLOR
    }
    
    # Icon mappings for dialog types (using Google Material Icons)
    TYPE_ICONS = {
        TYPE_INFO: "info_i",           # info_i icon
        TYPE_WARNING: "priority_high",   # exclamation icon
        TYPE_ERROR: "report",     # exclamation icon
        TYPE_SUCCESS: "check",         # check icon
        TYPE_QUESTION: "question_mark"          # help icon (keeping as is)
    }
    
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
        size: Optional[tuple] = None
    ):
        """
        Initialize the base message dialog.
        
        Args:
            parent: Parent widget
            title: Dialog window title
            message: Main message text to display
            dialog_type: Type of dialog (info, warning, error, success, question)
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
        self.is_resizable = resizable
        
        # Setup dialog properties
        self.setModal(modal)
        self.setWindowTitle(title)
        
        # Set size constraints
        if size:
            self.setFixedSize(QSize(*size))
        else:
            self.setMinimumSize(QSize(400, 200))
            if not resizable:
                self.setMaximumSize(QSize(600, 400))
        
        # Setup UI
        self._setup_fonts()
        self._setup_ui()
        self._apply_styling()
        self._connect_signals()
        
        # Position dialog
        self._center_on_parent()
    
    def _setup_fonts(self):
        """Setup font families for the dialog."""
        # Load Inter font for text
        inter_font_path = Path(__file__).parent.parent.parent / "microdrop_style" / "fonts" / "Inter-VariableFont_opsz,wght.ttf"
        self.text_font_family = load_font_family(inter_font_path) or "Inter"
        
        # Load Material Symbols for icons
        icon_font_path = Path(__file__).parent.parent.parent / "microdrop_style" / "icons" / "Material_Symbols_Outlined" / "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf"
        self.icon_font_family = load_font_family(icon_font_path) or ICON_FONT_FAMILY
    
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
        header_layout.setSpacing(5)
        header_layout.setAlignment(Qt.AlignTop)
        
        # Close button in top right corner
        close_layout = QHBoxLayout()
        close_layout.setContentsMargins(0, 0, 0, 5)  # Small margin below close button
        close_layout.addStretch()
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(32, 32)
        close_font = QFont(self.text_font_family)
        close_font.setPointSize(18)
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
                text_y_offset=self.TRIANGLE_TEXT_Y_OFFSET
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
    
    def _create_content(self):
        """Create the content area with message text."""
        self.content_frame = QFrame()
        self.content_frame.setObjectName("contentFrame")
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(25, 10, 25, 25)
        content_layout.setSpacing(15)
        
        # Message text
        self.message_label = QLabel(self.message_text)
        self.message_label.setObjectName("messageLabel")
        message_font = QFont(self.text_font_family)
        message_font.setPointSize(12)
        self.message_label.setFont(message_font)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        content_layout.addWidget(self.message_label)
        
        # Additional content area for subclasses
        self.additional_content_layout = QVBoxLayout()
        content_layout.addLayout(self.additional_content_layout)
        
        self.main_layout.addWidget(self.content_frame, 1)
    
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
        def button_sort_key(item):
            button_text, config = item
            # Exit/cancel buttons get priority 0 (leftmost)
            if (button_text.lower() in ["exit", "cancel", "close"] or 
                "discard" in button_text.lower() or
                "continue anyway" in button_text.lower()):
                return 0
            # All other buttons get priority 1 (rightward)
            else:
                return 1
        
        button_list.sort(key=button_sort_key)
        
        for i, (button_text, config) in enumerate(button_list):
            button = QPushButton(button_text)
            # Set proper object name for styling - Exit buttons get special styling
            if (button_text.lower() in ["exit", "cancel", "close"] or 
                "discard" in button_text.lower() or
                "continue anyway" in button_text.lower()):
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
                background-color: {self._darken_color(self.EXIT_BUTTON_COLOR, 0.05)};
                border-color: {self._darken_color(self.BORDER_COLOR, 0.1)};
            }}
            
            QPushButton#exitButton:pressed {{
                background-color: {self._darken_color(self.EXIT_BUTTON_COLOR, 0.1)};
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
            return {
                "Exit": {"action": self.reject},
                "Save": {"action": self.accept}
            }
        else:
            return {
                "Exit": {"action": self.reject},
                "OK": {"action": self.accept}
            }
    
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
        import sys
        import os
        
        if sys.platform == "darwin":
            try:
                import subprocess
                mode = subprocess.check_output(
                    "defaults read -g AppleInterfaceStyle",
                    shell=True
                ).strip()
                return mode == b"Dark"
            except Exception:
                return False
        elif sys.platform.startswith("win"):
            try:
                import winreg
                reg = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                key = winreg.OpenKey(
                    reg,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                )
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
            h, s, l, a = color.getHsl()
            l = max(0, int(l * (1 - factor)))
            new_color = QColor.fromHsl(h, s, l, a)
            return new_color.name()
        except:
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
        except:
            return "#F8F9FA"  # Fallback light gray
    
    def _get_icon_shape_style(self) -> str:
        """Get the appropriate shape styling for the icon based on dialog type."""
        if self.dialog_type == self.TYPE_SUCCESS:
            # Rounded square for success
            return "border-radius: 8px"
        elif self.dialog_type == self.TYPE_WARNING:
            # Create triangle effect using clip-path equivalent
            # Since CSS clip-path isn't well supported in Qt, we'll use a more rounded shape
            return "border-radius: 12px 12px 32px 12px"
        else:
            # Circle for info, error, and question
            return "border-radius: 32px"
    
    # Public methods for customization
    def set_message(self, message: str):
        """Update the message text."""
        self.message_text = message
        if hasattr(self, 'message_label'):
            self.message_label.setText(message)
    
    def set_title(self, title: str):
        """Update the dialog title."""
        self.title_text = title
        self.setWindowTitle(title)
        if hasattr(self, 'title_label'):
            self.title_label.setText(title)
    
    def add_content_widget(self, widget):
        """Add additional widget to content area."""
        if hasattr(self, 'additional_content_layout'):
            self.additional_content_layout.addWidget(widget)
    
    def add_details_with_copy(self, details_text: str, details_label: str = "Details:"):
        """Add a details section with copy to clipboard functionality."""
        # Details label
        label = QLabel(details_label)
        label_font = QFont(self.text_font_family)
        label_font.setPointSize(10)
        label_font.setWeight(QFont.Weight.Bold)
        label.setFont(label_font)
        label.setStyleSheet(f"color: {self.TEXT_COLOR};")
        
        # Container for text browser and copy button
        details_container = QFrame()
        container_layout = QVBoxLayout(details_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(5)
        
        # Text browser for details
        details_browser = QTextBrowser()
        details_browser.setMinimumHeight(100)
        details_browser.setMaximumHeight(200)
        # Convert markdown-like formatting to HTML for better display
        html_text = details_text.replace("**", "<b>", 1).replace("**", "</b>", 1)
        # Handle multiple bold sections
        import re
        html_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_text)
        # Replace newlines with HTML breaks for proper formatting
        html_text = html_text.replace('\n', '<br>')
        
        details_browser.setHtml(f"<div style='font-family: monospace; font-size: 11px;'>{html_text}</div>")
        
        # Header with copy button
        header_layout = QHBoxLayout()
        header_layout.addWidget(label)
        header_layout.addStretch()
        
        # Copy button with material icon
        copy_button = QPushButton("content_copy")
        copy_button.setObjectName("copyButton")
        copy_button.setToolTip("Copy to clipboard")
        copy_button.setFixedSize(60, 24)
        
        # Set material icon font
        copy_font = QFont(self.icon_font_family)
        copy_font.setPointSize(12)
        copy_button.setFont(copy_font)
        
        # Connect copy functionality
        copy_button.clicked.connect(lambda: self._copy_to_clipboard(details_text))
        
        header_layout.addWidget(copy_button)
        
        container_layout.addLayout(header_layout)
        container_layout.addWidget(details_browser)
        
        self.add_content_widget(details_container)
        return details_browser, copy_button
    
    def _copy_to_clipboard(self, text: str):
        """Copy text to system clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        # Optional: Show brief confirmation (could be expanded to a toast notification)
        print(f"Copied to clipboard: {len(text)} characters")
    
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
            if (new_text.lower() in ["exit", "cancel", "close"] or 
                "discard" in new_text.lower() or
                "continue anyway" in new_text.lower()):
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
        **kwargs
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
            **kwargs
        )
        return dialog.show_dialog()
