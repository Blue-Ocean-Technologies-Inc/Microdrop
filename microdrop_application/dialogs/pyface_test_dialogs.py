"""Dialog example with buttons to test Pyface dialogs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from pyface.api import ApplicationWindow, GUI
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import (
    QLabel,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logger.logger_service import LEVELS, get_logger, init_logger
from microdrop_application.dialogs.logger_integration import (
    disable_dialog_logging,
    enable_dialog_logging,
)
from microdrop_application.dialogs.pyface_wrapper import (
    YES,
    confirm,
    error,
    information,
    success,
    warning,
)


class MainWindow(ApplicationWindow):
    """The main application window with buttons to test dialogs."""

    def __init__(self, **traits):
        """Creates a new application window."""
        super().__init__(**traits)
        self.title = "Pyface Dialog Test"
        self._logger_initialized = False

    def _add_button_group(self, layout, title, buttons):
        """Helper to add a group of buttons to the layout."""
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        button_layout = QHBoxLayout()

        for text, handler in buttons:
            button = QPushButton(text)
            button.clicked.connect(handler)
            button.setMinimumHeight(40)
            button_layout.addWidget(button)

        group_layout.addLayout(button_layout)
        layout.addWidget(group)

    def _create_contents(self, parent):
        """Create the dialog test buttons."""
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel("Pyface Dialog Test")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setWeight(QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel("Click the buttons below to test different Pyface dialogs.")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)

        # Basic dialogs group
        self._add_button_group(
            layout,
            "Basic Dialogs",
            [
                ("Information", self.test_information),
                ("Success", self.test_success),
                ("Confirm", self.test_confirm),
                ("Warning", self.test_warning),
                ("Error", self.test_error),
            ],
        )

        # Advanced examples group
        self._add_button_group(
            layout,
            "Advanced Examples",
            [
                ("Warning with RTF", self.test_warning_rtf),
                ("Confirm with Details", self.test_confirm_details),
                ("Error with Details", self.test_error_details),
                ("Info with Details", self.test_information_details),
                ("Success with Details", self.test_success_details),
                ("Confirm Simple Details", self.test_confirm_simple_details),
            ],
        )

        # Logger integration group
        self._add_button_group(
            layout,
            "Logger Integration",
            [
                ("Enable Dialog Logging", self.enable_logging),
                ("Disable Dialog Logging", self.disable_logging),
                ("Log Info", self.log_info_dialog),
                ("Log Warning", self.log_warning_dialog),
                ("Log Error", self.log_error_dialog),
                ("Log Critical", self.log_critical_dialog),
            ],
        )

        layout.addStretch()
        return widget

    # ------------------------------------------------------------------------
    # Dialog test methods
    # ------------------------------------------------------------------------

    def test_information(self):
        """Test information dialog."""
        msg = "This is an information dialog."
        information(
            parent=self.control,
            message=msg,
            title="Information",
            # cancel=True
        )

    def test_warning(self):
        """Test basic warning dialog."""
        msg = "This is a warning dialog.\n\n" "It uses the BaseMessageDialog system with warning styling."
        warning(parent=self.control, message=msg, title="Warning", cancel=True)

    def test_success(self):
        """Test basic success dialog."""
        msg = "Operation completed successfully.\n\n" "Everything looks good."
        success(parent=self.control, message=msg, title="Success")

    def test_confirm(self):
        """Test basic confirm dialog using wrapper."""
        if confirm(parent=self.control, message="Should I proceed?", title="Confirm") == YES:
            print("User chose YES")
        else:
            print("User chose NO")

    def test_error(self):
        """Test error dialog using wrapper."""
        error(
            parent=self.control,
            message="This is an error dialog using the styled wrapper.",
            title="Error",
        )

    def test_warning_rtf(self):
        """Test warning dialog with RTF content."""
        img_path = Path(__file__).parents[2] / "dropbot_status" / "images" / "dropbot-power.png"
        print(img_path)
        img_path = img_path.as_posix()
        rtf_content = (
            "<p>A new version is ready to be installed.</p>\n"
            "<b>What's new:</b>\n"
            "<ul>\n"
            "    <li>Added <i>cool new features</i>.</li>\n"
            '    <li>Fixed the <font color="red">annoying bug</font>.</li>\n'
            "</ul>\n"
            '<a href="https://example.com">Read the release notes</a>'
        )

        with_image_content = (
            f"<p>Please ensure the device is connected as shown below:</p>\n"
            f'<img src="{img_path}" width="250">\n'
            f"<p>Connect both the power adapter and the USB cable before "
            f"proceeding.</p>"
        )

        # Note: wrapper's warning() uses 'detail' parameter for details
        # The informative content can be included in the detail
        combined_content = f"{rtf_content}\n\n{with_image_content}"
        details = f"This is some details over here in html format\n{rtf_content}"

        warning(
            parent=self.control,
            message=combined_content,
            title="Warning",
            detail=details,
        )

    def test_confirm_details(self):
        """Test confirm dialog with details using wrapper."""
        rtf_content = (
            "<p>A new version is ready to be installed.</p>\n"
            "<b>What's new:</b>\n"
            "<ul>\n"
            "    <li>Added <i>cool new features</i>.</li>\n"
            '    <li>Fixed the <font color="red">annoying bug</font>.</li>\n'
            "</ul>\n"
            '<a href="https://example.com">Read the release notes</a>'
        )

        detail_text = (
            "This is some details over here in the collapsible section.\n"
            "You can include additional information that users can expand "
            "to see more details."
        )

        if (
            confirm(
                parent=self.control,
                message="Should I exit?",
                title="Confirm Exit",
                cancel=False,
                no_label="Nope",
                yes_label="Just Do It",
                informative=rtf_content,
                detail=detail_text,
                text_format="auto",
            )
            == YES
        ):
            print("User chose YES")

    def test_error_details(self):
        """Test error dialog with details using wrapper."""
        rtf_content = (
            "<p>An error occurred while processing your request.</p>\n"
            "<b>Error details:</b>\n"
            "<ul>\n"
            "    <li>Failed to connect to server</li>\n"
            "    <li>Timeout after 30 seconds</li>\n"
            "</ul>"
        )

        detail_text = (
            "**Traceback (most recent call last):**\n"
            '  File "example.py", line 42, in process_data\n'
            "    result = api_call()\n"
            '  File "api.py", line 15, in api_call\n'
            '    raise ConnectionError("Server unreachable")\n'
            "ConnectionError: Server unreachable"
        )

        error(
            parent=self.control,
            message="Operation failed",
            title="Error",
            informative=rtf_content,
            detail=detail_text,
            text_format="auto",
        )

    def test_information_details(self):
        """Test information dialog with details."""
        msg = "Analysis complete."
        details = (
            "Processed 150 samples.\n"
            "Average signal: 45.2\n"
            "Standard deviation: 2.1\n"
            "All parameters within normal range."
        )
        information(
            parent=self.control,
            message=msg,
            title="Analysis Info",
            detail=details,
        )

    def test_success_details(self):
        """Test success dialog with details."""
        msg = "Data export successful."
        details = (
            "File saved to: C:/Users/Docs/export.csv\n"
            "Size: 1.2 MB\n"
            "Rows: 1500\n"
            "Columns: 12"
        )
        success(
            parent=self.control,
            message=msg,
            title="Export Success",
            detail=details,
        )

    def test_confirm_simple_details(self):
        """Test confirm dialog with simple details (no RTF)."""
        msg = "Are you sure you want to delete the selected items?"
        details = (
            "Items to delete:\n"
            "- Sample_001.dat\n"
            "- Sample_002.dat\n"
            "- Sample_003.dat\n\n"
            "This action cannot be undone."
        )
        if (
            confirm(
                parent=self.control,
                message=msg,
                title="Confirm Delete",
                detail=details,
                yes_label="Delete",
                no_label="Cancel",
            )
            == YES
        ):
            print("User chose Delete")

    def log_info_dialog(self):
        """Log an info message and show the dialog."""
        self._log_dialog_message("info", "Info log message from test dialog")

    def log_warning_dialog(self):
        """Log a warning message and show the dialog."""
        self._log_dialog_message("warning", "Warning log message from test dialog")

    def log_error_dialog(self):
        """Log an error message and show the dialog."""
        self._log_dialog_message("error", "Error log message from test dialog")

    def log_critical_dialog(self):
        """Log a critical message and show the dialog."""
        self._log_dialog_message("critical", "Critical log message from test dialog")

    def _log_dialog_message(self, level: str, message: str):
        logger = get_logger("microdrop.pyface_test")
        log_method = getattr(logger, level)
        log_method(message, extra={"show_dialog": True})

    def enable_logging(self):
        """Enable global dialog logging."""
        if not self._logger_initialized:
            init_logger(preferred_log_level=LEVELS["INFO"])
            get_logger("microdrop.pyface_test").setLevel(LEVELS["INFO"])
            self._logger_initialized = True
        enable_dialog_logging()

    def disable_logging(self):
        """Disable global dialog logging."""
        disable_dialog_logging()


# Application entry point.
if __name__ == "__main__":
    # Create the GUI (this does NOT start the GUI event loop).
    gui = GUI()
    # Create and open the main window.
    window = MainWindow()
    window.open()
    # Start the GUI event loop!
    gui.start_event_loop()
