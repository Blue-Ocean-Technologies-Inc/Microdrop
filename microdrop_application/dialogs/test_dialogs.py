#!/usr/bin/env python3
"""
Standalone Dialog Test Application

A simple test application to demonstrate and test all custom dialog types.
Run this file directly to open a test interface with buttons for each dialog type.

Usage:
    python test_dialogs.py
"""

import sys
import os
import logging
from pathlib import Path

# Add the project root to Python path so we can import the dialog modules
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QGroupBox, QScrollArea, QCheckBox, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

# Import our custom dialog system
from microdrop_application.dialogs import (
    show_error_alert, show_success, show_information, show_question,
    show_detection_issue, UnsavedChangesDialog, ErrorAlertDialog, 
    SuccessDialog, InformationDialog, DetectionIssueDialog
)
from microdrop_application.dialogs.base_message_dialog import BaseMessageDialog
from microdrop_application.dialogs.logger_integration import DialogLogger


class DialogTestWindow(QMainWindow):
    """Main test window with buttons for all dialog types."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Microdrop Custom Dialog Test Suite")
        self.setMinimumSize(800, 600)
        
        # Setup logger for testing logger integration
        self.dialog_logger = DialogLogger("test.dialogs", show_dialogs=True)
        
        # Ensure the logger has a console handler for CLI output
        if not self.dialog_logger.logger.handlers:
            # Add console handler if none exists
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s:%(name)s]: %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            self.dialog_logger.logger.addHandler(console_handler)
            self.dialog_logger.logger.setLevel(logging.DEBUG)
        
        self.setup_ui()
        self.center_window()
    
    def setup_ui(self):
        """Setup the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("Microdrop Dialog Test Suite")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setWeight(QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Click the buttons below to test different dialog types. "
            "Each dialog demonstrates the styling and functionality "
            "of the custom messaging system."
        )
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(desc_label)
        
        # Scroll area for all the test sections
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15)
        
        # Basic dialogs section
        self.create_basic_dialogs_section(scroll_layout)
        
        # Advanced dialogs section
        self.create_advanced_dialogs_section(scroll_layout)
        
        # Logger integration section
        self.create_logger_integration_section(scroll_layout)
        
        # Custom examples section
        self.create_custom_examples_section(scroll_layout)
        
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        
        # Status bar
        self.statusBar().showMessage("Ready to test dialogs")
    
    def decode_dialog_result(self, result: int) -> str:
        """
        Convert dialog result code to a meaningful name.
        
        Args:
            result: The result code from dialog.show_dialog()
            
        Returns:
            Human-readable string describing the result
        """
        result_names = {
            BaseMessageDialog.RESULT_CANCEL: "Cancel",
            BaseMessageDialog.RESULT_OK: "OK",
            BaseMessageDialog.RESULT_SAVE: "Save", 
            BaseMessageDialog.RESULT_RESTART: "Restart",
            BaseMessageDialog.RESULT_CONTINUE: "Continue",
            BaseMessageDialog.RESULT_YES: "Yes",
            BaseMessageDialog.RESULT_NO: "No",
            BaseMessageDialog.RESULT_PAUSE: "Pause"
        }
        
        result_name = result_names.get(result, f"Unknown({result})")
        return f"{result_name} (code: {result})"
    
    def create_basic_dialogs_section(self, parent_layout):
        """Create the basic dialogs test section."""
        group_box = QGroupBox("Basic Dialog Types")
        layout = QVBoxLayout(group_box)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        buttons = [
            ("Information Dialog", self.show_info_dialog),
            ("Success Dialog", self.show_success_dialog),
            ("Warning Dialog", self.show_warning_dialog),
            ("Error Dialog", self.show_error_dialog),
        ]
        
        for text, handler in buttons:
            button = QPushButton(text)
            button.clicked.connect(handler)
            button.setMinimumHeight(40)
            button_layout.addWidget(button)
        
        layout.addLayout(button_layout)
        parent_layout.addWidget(group_box)
    
    def create_advanced_dialogs_section(self, parent_layout):
        """Create the advanced dialogs test section."""
        group_box = QGroupBox("Advanced Dialog Features")
        layout = QVBoxLayout(group_box)
        
        # First row
        button_layout1 = QHBoxLayout()
        buttons1 = [
            ("Error with Details", self.show_error_with_details),
            ("Question Dialog", self.show_question_dialog),
            ("Unsaved Changes", self.show_unsaved_changes),
        ]
        
        for text, handler in buttons1:
            button = QPushButton(text)
            button.clicked.connect(handler)
            button.setMinimumHeight(40)
            button_layout1.addWidget(button)
        
        # Second row
        button_layout2 = QHBoxLayout()
        buttons2 = [
            ("Custom Buttons", self.show_custom_buttons),
            ("Large Dialog", self.show_large_dialog),
            ("Non-Modal Dialog", self.show_non_modal_dialog),
        ]
        
        for text, handler in buttons2:
            button = QPushButton(text)
            button.clicked.connect(handler)
            button.setMinimumHeight(40)
            button_layout2.addWidget(button)
        
        layout.addLayout(button_layout1)
        layout.addLayout(button_layout2)
        parent_layout.addWidget(group_box)
    
    def create_logger_integration_section(self, parent_layout):
        """Create the logger integration test section."""
        group_box = QGroupBox("Logger Integration Tests")
        layout = QVBoxLayout(group_box)
        
        # Enable/disable dialogs checkbox
        self.logger_enabled_checkbox = QCheckBox("Enable Logger Dialogs")
        self.logger_enabled_checkbox.setChecked(True)
        self.logger_enabled_checkbox.stateChanged.connect(
            self.toggle_logger_dialogs
        )
        layout.addWidget(self.logger_enabled_checkbox)
        
        # Logger test buttons
        button_layout = QHBoxLayout()
        buttons = [
            ("Log Error", self.log_error),
            ("Log Warning", self.log_warning),
            ("Log Info", self.log_info),
            ("Log Success", self.log_success),
        ]
        
        for text, handler in buttons:
            button = QPushButton(text)
            button.clicked.connect(handler)
            button.setMinimumHeight(40)
            button_layout.addWidget(button)
        
        layout.addLayout(button_layout)
        parent_layout.addWidget(group_box)
    
    def create_custom_examples_section(self, parent_layout):
        """Create the custom examples section."""
        group_box = QGroupBox("Real-World Examples")
        layout = QVBoxLayout(group_box)
        
        button_layout1 = QHBoxLayout()
        buttons1 = [
            ("Connection Error", self.show_connection_error),
            ("Save Success", self.show_save_success),
            ("Protocol Warning", self.show_protocol_warning),
            ("Device Info", self.show_device_info),
            ("Droplet Detection Issue", self.show_detection_issue_dialog),
        ]
        
        for text, handler in buttons1:
            button = QPushButton(text)
            button.clicked.connect(handler)
            button.setMinimumHeight(40)
            button_layout1.addWidget(button)
        
        layout.addLayout(button_layout1)
        parent_layout.addWidget(group_box)
    
    def center_window(self):
        """Center the window on the screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        window_geometry = self.geometry()
        x = (screen.width() - window_geometry.width()) // 2
        y = (screen.height() - window_geometry.height()) // 2
        self.move(x, y)
    
    # Basic dialog methods
    def show_info_dialog(self):
        """Show an information dialog."""
        result = show_information(
            parent=self,
            title="Information",
            message="This is an information dialog. It provides general "
                   "information to the user without requiring immediate action."
        )
        self.statusBar().showMessage(f"Information dialog result: {self.decode_dialog_result(result)}")
    
    def show_success_dialog(self):
        """Show a success dialog."""
        result = show_success(
            parent=self,
            title="Success",
            message="The operation completed successfully! All files have "
                   "been processed and saved to the specified location."
        )
        self.statusBar().showMessage(f"Success dialog result: {self.decode_dialog_result(result)}")
    
    def show_warning_dialog(self):
        """Show a warning dialog using UnsavedChangesDialog."""
        dialog = UnsavedChangesDialog(
            parent=self,
            title="Warning",
            message="This is a warning dialog. It alerts the user to "
                   "potential issues that may require attention."
        )
        result = dialog.show_dialog()
        self.statusBar().showMessage(f"Warning dialog result: {self.decode_dialog_result(result)}")
    
    def show_error_dialog(self):
        """Show a basic error dialog."""
        result = show_error_alert(
            parent=self,
            title="Error",
            message="An error has occurred while processing your request. "
                   "Please check your settings and try again."
        )
        self.statusBar().showMessage(f"Error dialog result: {self.decode_dialog_result(result)}")
    
    # Advanced dialog methods
    def show_error_with_details(self):
        """Show an error dialog with technical details."""
        result = show_error_alert(
            parent=self,
            title="Connection Error",
            message="Failed to connect to the DropBot device. Please check "
                   "the connection and try again.",
            error_details="""Traceback (most recent call last):
  File "dropbot_controller.py", line 123, in connect_device
    device = serial.Serial(port, baudrate=115200, timeout=5)
  File "/usr/lib/python3.9/site-packages/serial/__init__.py", line 240
    raise SerialException(msg.errno, "could not open port {}: {}".format(self._port, msg))
serial.serialutil.SerialException: [Errno 2] could not open port /dev/ttyUSB0: [Errno 2] No such file or directory: '/dev/ttyUSB0'"""
        )
        self.statusBar().showMessage(f"Error with details result: {self.decode_dialog_result(result)}")
    
    def show_question_dialog(self):
        """Show a question dialog."""
        result = show_question(
            parent=self,
            title="Confirm Action",
            message="Are you sure you want to delete the selected protocol? "
                   "This action cannot be undone.",
            yes_text="Delete",
            no_text="Cancel"
        )
        action = "Delete" if result == BaseMessageDialog.Accepted else "Cancel"
        self.statusBar().showMessage(f"Question dialog: User chose {action}")
    
    def show_detection_issue_dialog(self):
        """Show a detection issue dialog with expected vs actual results."""
        result = show_detection_issue(
            parent=self,
            title="Droplet Detection Issue",
            message="Some droplets weren't detected during this step.\nContinuing may affect the results of xxxxxx.",
            question="Would you like to continue with the protocol or pause and review?",
            expected="droplets at electrode032, electrode047, electrode020",
            detected="droplets at None",
            missing="droplets at electrode032, electrode047, electrode020"
        )
        self.statusBar().showMessage(f"Detection issue result: {self.decode_dialog_result(result)}")
    
    def show_unsaved_changes(self):
        """Show an unsaved changes dialog."""
        dialog = UnsavedChangesDialog(
            parent=self,
            message="You have unsaved changes to the current experiment. "
                   "What would you like to do?"
        )
        result = dialog.show_dialog()
        action = "Save" if result == BaseMessageDialog.Accepted else "Exit"
        self.statusBar().showMessage(f"Unsaved changes: User chose {action}")
    
    def show_custom_buttons(self):
        """Show a dialog with custom button configuration."""
        from microdrop_application.dialogs.message_dialog_types import (
            CustomActionDialog
        )
        
        # Define actions that include closing the dialog
        def handle_restart_and_close():
            self.handle_restart()
            dialog.close_with_result(BaseMessageDialog.RESULT_RESTART)
            
        def handle_continue_and_close():
            self.handle_continue()
            dialog.close_with_result(BaseMessageDialog.RESULT_CONTINUE)
            
        def handle_cancel_and_close():
            self.handle_cancel()
            dialog.close_with_result(BaseMessageDialog.RESULT_CANCEL)
        
        custom_buttons = {
            "Restart": {"action": handle_restart_and_close},
            "Continue": {"action": handle_continue_and_close},
            "Cancel": {"action": handle_cancel_and_close}
        }
        
        dialog = CustomActionDialog(
            parent=self,
            title="System Update Required",
            message="A system update is available. Choose how to proceed:",
            custom_buttons=custom_buttons,
            dialog_type=BaseMessageDialog.TYPE_QUESTION
        )
        
        result = dialog.show_dialog()
        self.statusBar().showMessage(f"Custom buttons result: {self.decode_dialog_result(result)}")
    
    def show_large_dialog(self):
        """Show a larger dialog with more content."""
        large_message = """This is a demonstration of a larger dialog with more content.

The dialog system automatically handles text wrapping and can accommodate longer messages. This is useful for:

• Detailed error explanations
• Step-by-step instructions
• Important warnings or notices
• Configuration information
• Help text and documentation

The dialog will automatically size itself appropriately while maintaining good readability and visual hierarchy."""
        
        result = show_information(
            parent=self,
            title="Large Content Dialog",
            message=large_message,
            size=(600, 400)
        )
        self.statusBar().showMessage(f"Large dialog result: {self.decode_dialog_result(result)}")
    
    def show_non_modal_dialog(self):
        """Show a non-modal dialog."""
        dialog = InformationDialog(
            parent=self,
            title="Non-Modal Dialog",
            message="This is a non-modal dialog. You can interact with the "
                   "main window while this dialog is open.",
            modal=False
        )
        dialog.show()  # Use show() instead of show_dialog() for non-modal
        self.statusBar().showMessage("Non-modal dialog opened")
    
    # Logger integration methods
    def toggle_logger_dialogs(self, state):
        """Toggle logger dialog display."""
        if state == Qt.Checked:
            self.dialog_logger.enable_dialogs()
            self.statusBar().showMessage("Logger dialogs enabled")
        else:
            self.dialog_logger.disable_dialogs()
            self.statusBar().showMessage("Logger dialogs disabled")
    
    def log_error(self):
        """Log an error message."""
        error_msg = ("This is an error logged through the logger integration system. "
                    "It automatically shows a dialog when dialogs are enabled.")
        
        # Use the dialog logger method which should log to console AND show dialog
        self.dialog_logger.error_with_dialog(error_msg)
        
        self.statusBar().showMessage("Error logged")
    
    def log_warning(self):
        """Log a warning message."""
        warning_msg = ("This is a warning message from the logger. It shows as a "
                      "warning-style dialog.")
        
        # Use the dialog logger method which should log to console AND show dialog
        self.dialog_logger.warning_with_dialog(warning_msg)
        
        self.statusBar().showMessage("Warning logged")
    
    def log_info(self):
        """Log an info message."""
        info_msg = "This is an informational message from the logger system."
        
        # Use the dialog logger method which should log to console AND show dialog
        self.dialog_logger.info_with_dialog(info_msg)
        
        self.statusBar().showMessage("Info logged")
    
    def log_success(self):
        """Log a success message."""
        success_msg = "This is a success message logged through the system!"
        
        # Use the dialog logger method which should log to console AND show dialog
        self.dialog_logger.success_with_dialog(success_msg)
        
        self.statusBar().showMessage("Success logged")
    
    # Real-world example methods
    def show_connection_error(self):
        """Show a realistic connection error."""
        result = show_error_alert(
            parent=self,
            title="DropBot Connection Failed",
            message="Unable to establish connection with DropBot device.\n\n"
                   "Please check:\n"
                   "• Device is powered on\n"
                   "• USB cable is securely connected\n"
                   "• Device drivers are properly installed\n"
                   "• No other applications are using the device",
            error_details="SerialException: could not open port /dev/ttyUSB0"
        )
        self.statusBar().showMessage("Connection error dialog shown")
    
    def show_save_success(self):
        """Show a realistic save success message."""
        result = show_success(
            parent=self,
            title="Protocol Saved",
            message="Protocol 'Mixing_Experiment_v2.json' has been saved "
                   "successfully to the protocols folder."
        )
        self.statusBar().showMessage("Save success dialog shown")
    
    def show_protocol_warning(self):
        """Show a realistic protocol warning."""
        result = show_question(
            parent=self,
            title="Unsaved Protocol Changes",
            message="You have made changes to the current protocol that "
                   "haven't been saved.\n\nSave changes before switching "
                   "to a different protocol?",
            yes_text="Save Changes",
            no_text="Discard Changes"
        )
        action = "Save" if result == BaseMessageDialog.Accepted else "Discard"
        self.statusBar().showMessage(f"Protocol warning: {action}")
    
    def show_device_info(self):
        """Show realistic device information."""
        device_info = """DropBot Device Information:

Model: DropBot DX-3.1
Firmware: v3.1.2-stable
Serial: DB31-2023-0842
Status: Connected

Capabilities:
• 120 electrode channels
• High voltage switching
• Real-time monitoring
• Temperature sensor
• Integrated power supply

Last calibration: 2024-01-15
Connection: USB (/dev/ttyUSB0)"""
        
        result = show_information(
            parent=self,
            title="Device Information",
            message=device_info
        )
        self.statusBar().showMessage("Device info dialog shown")
    
    # Callback methods
    def handle_restart(self):
        """Handle restart action."""
        self.statusBar().showMessage("Restart action triggered")
    
    def handle_continue(self):
        """Handle continue action."""
        self.statusBar().showMessage("Continue action triggered")
    
    def handle_cancel(self):
        """Handle cancel action."""
        self.statusBar().showMessage("Cancel action triggered")


def main():
    """Run the standalone dialog test application."""
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Microdrop Dialog Test Suite")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Microdrop")
    
    # Create and show main window
    window = DialogTestWindow()
    window.show()
    
    # Start event loop
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
