"""
Example usage of the custom messaging dialog system.

This module demonstrates how to use the various dialog types and logger integration
within the Microdrop application.
"""

import logging
from typing import Optional
from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QApplication
from PySide6.QtCore import Qt

from .message_dialog_types import (
    UnsavedChangesDialog, ErrorAlertDialog, SuccessDialog, 
    InformationDialog, QuestionDialog, show_error_alert,
    show_success, show_information, show_question
)
from .base_message_dialog import BaseMessageDialog
from .logger_integration import DialogLogger, enable_dialog_logging, disable_dialog_logging


# Example 1: Basic dialog usage
def example_basic_dialogs(parent: Optional[QWidget] = None):
    """Demonstrate basic dialog usage."""
    
    # Simple information dialog
    result = show_information(
        parent=parent,
        title="Welcome",
        message="Welcome to Microdrop Next Gen! This is an information dialog."
    )
    print(f"Information dialog result: {result}")
    
    # Success notification
    result = show_success(
        parent=parent,
        title="Operation Complete",
        message="Your settings have been saved successfully!"
    )
    print(f"Success dialog result: {result}")
    
    # Error alert with details
    result = show_error_alert(
        parent=parent,
        title="Connection Error",
        message="Failed to connect to DropBot device. Please check the connection and try again.",
        error_details="ConnectionError: [Errno 2] No such file or directory: '/dev/ttyUSB0'"
    )
    print(f"Error dialog result: {result}")
    
    # Question dialog
    result = show_question(
        parent=parent,
        title="Confirm Action",
        message="Are you sure you want to delete this protocol?",
        yes_text="Delete",
        no_text="Cancel"
    )
    print(f"Question dialog result: {result}")


# Example 2: Custom dialog with specific styling
def example_custom_dialog(parent: Optional[QWidget] = None):
    """Demonstrate custom dialog creation."""
    
    # Custom error dialog with specific configuration
    dialog = ErrorAlertDialog(
        parent=parent,
        title="Critical System Error",
        message="A critical error has occurred in the dropbot controller. The system will need to be restarted.",
        error_details="Exception in dropbot_controller.services.monitor: Device communication timeout after 30 seconds",
        size=(500, 350),
        modal=True
    )
    
    # Connect to custom actions
    def handle_restart():
        print("Restart action triggered")
        dialog.accept()
    
    def handle_continue():
        print("Continue action triggered")
        dialog.reject()
    
    # Get buttons and connect custom actions
    save_button = dialog.get_button("Save")
    if save_button:
        save_button.setText("Restart System")
        save_button.clicked.connect(handle_restart)
    
    exit_button = dialog.get_button("Exit")
    if exit_button:
        exit_button.setText("Continue Anyway")
        exit_button.clicked.connect(handle_continue)
    
    result = dialog.show_dialog()
    print(f"Custom dialog result: {result}")


# Example 3: Logger integration
def example_logger_integration():
    """Demonstrate logger integration with dialogs."""
    
    # Create a dialog-enabled logger
    dialog_logger = DialogLogger("microdrop.example", show_dialogs=True)
    
    # Regular logging (won't show dialogs)
    dialog_logger.logger.info("This is a regular info message")
    dialog_logger.logger.debug("This is a debug message")
    
    # Logging with dialog display
    dialog_logger.info_with_dialog("This info message will show a dialog!")
    dialog_logger.warning_with_dialog("This is a warning that appears in a dialog")
    dialog_logger.error_with_dialog("This error will be displayed in a popup dialog")
    dialog_logger.success_with_dialog("Operation completed successfully!")
    
    # Disable dialogs
    dialog_logger.disable_dialogs()
    dialog_logger.error_with_dialog("This error won't show a dialog")
    
    # Re-enable dialogs
    dialog_logger.enable_dialogs()
    dialog_logger.error_with_dialog("This error will show a dialog again")


# Example 4: Global logger integration
def example_global_logger_integration():
    """Demonstrate global logger integration."""
    
    # Enable dialog logging for all loggers
    enable_dialog_logging()
    
    # Now any logger can trigger dialogs
    logger = logging.getLogger("microdrop.test")
    
    # This will show a dialog because it's WARNING level
    logger.warning("Global warning message with dialog")
    
    # This will show a dialog because it has the flag
    logger.info("Info message with dialog", extra={'show_dialog': True})
    
    # Disable dialog logging
    disable_dialog_logging()
    
    # This won't show a dialog
    logger.error("Error without dialog")


# Example 5: Integration with application logger
def example_application_integration():
    """Demonstrate integration with the existing Microdrop logger."""
    
    from logger.logger_service import get_logger
    
    # Get the existing application logger
    logger = get_logger(__name__)
    
    # Add dialog capability to existing logger
    from .logger_integration import add_dialog_handler_to_logger
    dialog_handler = add_dialog_handler_to_logger(logger.name, show_dialogs=True)
    
    # Now the application logger can show dialogs
    logger.critical("Critical application error!", extra={'show_dialog': True})
    logger.error("Device connection failed!", extra={'show_dialog': True})
    
    # Configure dialog behavior
    from .logger_integration import DialogConfig
    dialog_handler.update_config('CRITICAL', DialogConfig(
        dialog_type=BaseMessageDialog.TYPE_ERROR,
        title="Critical Application Error",
        show_details=True,
        modal=True
    ))
    
    logger.critical("Another critical error with custom config", extra={'show_dialog': True})


# Example 6: Testing widget
class DialogTestWidget(QWidget):
    """Test widget to demonstrate all dialog types."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dialog Test Widget")
        self.setMinimumSize(300, 400)
        
        layout = QVBoxLayout(self)
        
        # Create test buttons
        buttons = [
            ("Show Information", self.show_info),
            ("Show Success", self.show_success),
            ("Show Warning", self.show_warning),
            ("Show Error", self.show_error),
            ("Show Question", self.show_question),
            ("Show Unsaved Changes", self.show_unsaved),
            ("Test Logger Integration", self.test_logger),
            ("Enable Dialog Logging", self.enable_logging),
            ("Disable Dialog Logging", self.disable_logging),
        ]
        
        for text, handler in buttons:
            button = QPushButton(text)
            button.clicked.connect(handler)
            layout.addWidget(button)
        
        # Setup logger for testing
        self.dialog_logger = DialogLogger("dialog.test", show_dialogs=True)
    
    def show_info(self):
        show_information(
            parent=self,
            title="Information",
            message="This is an information dialog for testing purposes."
        )
    
    def show_success(self):
        show_success(
            parent=self,
            title="Success",
            message="Operation completed successfully! All tests passed."
        )
    
    def show_warning(self):
        dialog = UnsavedChangesDialog(
            parent=self,
            title="Unsaved Changes",
            message="You have unsaved protocol changes. Save before closing?"
        )
        result = dialog.show_dialog()
        print(f"Warning dialog result: {result}")
    
    def show_error(self):
        show_error_alert(
            parent=self,
            title="Connection Error",
            message="Failed to connect to DropBot device.",
            error_details="Traceback (most recent call last):\n  File example.py, line 42\n    raise ConnectionError('Device not found')\nConnectionError: Device not found"
        )
    
    def show_question(self):
        result = show_question(
            parent=self,
            title="Confirm Delete",
            message="Are you sure you want to delete this protocol step?",
            yes_text="Delete",
            no_text="Cancel"
        )
        print(f"Question result: {result}")
    
    def show_unsaved(self):
        dialog = UnsavedChangesDialog(
            parent=self,
            message="Your current experiment has unsaved changes. What would you like to do?"
        )
        result = dialog.show_dialog()
        print(f"Unsaved changes result: {result}")
    
    def test_logger(self):
        self.dialog_logger.error_with_dialog("Test error message from logger integration")
        self.dialog_logger.warning_with_dialog("Test warning message")
        self.dialog_logger.success_with_dialog("Test success message")
    
    def enable_logging(self):
        enable_dialog_logging()
        logging.getLogger("test").warning("Dialog logging enabled - this should show a popup")
    
    def disable_logging(self):
        disable_dialog_logging()
        logging.getLogger("test").error("Dialog logging disabled - this should NOT show a popup")


# Example 7: Running the test widget
def run_dialog_test():
    """Run the dialog test widget as a standalone application."""
    app = QApplication.instance() or QApplication([])
    
    widget = DialogTestWidget()
    widget.show()
    
    return widget


if __name__ == "__main__":
    # Run examples
    print("Running dialog examples...")
    
    # Initialize Qt application
    QApplication.instance() or QApplication([])
    
    # Run test widget
    run_dialog_test()
    
    # Keep application running
    # app.exec()
