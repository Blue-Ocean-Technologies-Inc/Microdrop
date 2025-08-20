"""
Specific dialog type implementations for different message cases.

This module provides specialized dialog classes that inherit from BaseMessageDialog
and implement specific behaviors for different types of user interactions.
"""

from typing import Optional, Dict, Any
from PySide6.QtWidgets import QLabel, QTextBrowser
from PySide6.QtGui import QFont

from .base_message_dialog import BaseMessageDialog


class UnsavedChangesDialog(BaseMessageDialog):
    """
    Dialog for handling unsaved changes scenarios.
    
    Shows a warning icon and provides options to save, discard,
    or cancel.
    """
    
    def __init__(
        self,
        parent=None,
        title: str = "Unsaved Changes",
        message: str = "You have unsaved changes. If you exit now, "
                       "they will be lost. Save before leaving.",
        **kwargs
    ):
        buttons = {
            "Discard Changes": {"action": self.discard_changes},
            "Save Changes": {"action": self.save_changes}
        }
        
        super().__init__(
            parent=parent,
            title=title,
            message=message,
            dialog_type=self.TYPE_WARNING,
            buttons=buttons,
            **kwargs
        )
        
        # Note: Icon is automatically set by base class based on dialog_type
    
    def save_changes(self):
        """Handle save action."""
        self.button_clicked.emit("Save")
        self.accept()
    
    def discard_changes(self):
        """Handle discard/exit action."""
        self.button_clicked.emit("Exit")
        self.reject()


class ErrorAlertDialog(BaseMessageDialog):
    """
    Dialog for displaying error messages and alerts.
    
    Shows an error icon and provides detailed error information.
    """
    
    def __init__(
        self,
        parent=None,
        title: str = "Error Alert",
        message: str = "Error text goes here describing the issue "
                       "and how to fix it.",
        error_details: Optional[str] = None,
        **kwargs
    ):
        buttons = {
            "Exit": {"action": self.close_dialog},
            "Save": {"action": self.acknowledge_error}
        }
        
        # Set default size for error dialogs with details to be larger
        if error_details and 'size' not in kwargs:
            kwargs['size'] = (600, 450)  # Larger default size for error dialogs with details
        
        super().__init__(
            parent=parent,
            title=title,
            message=message,
            dialog_type=self.TYPE_ERROR,
            buttons=buttons,
            **kwargs
        )
        
        # Add error details if provided
        if error_details:
            self._add_error_details(error_details)
    
    def _add_error_details(self, details: str):
        """Add expandable error details section with copy functionality."""
        self.add_details_with_copy(details, "Error Details:")
    
    def acknowledge_error(self):
        """Handle error acknowledgment."""
        self.button_clicked.emit("Save")
        self.accept()
    
    def close_dialog(self):
        """Handle close action."""
        self.button_clicked.emit("Exit")
        self.reject()


class SuccessDialog(BaseMessageDialog):
    """
    Dialog for displaying success messages and confirmations.
    
    Shows a success icon and provides positive feedback to users.
    """
    
    def __init__(
        self,
        parent=None,
        title: str = "Success",
        message: str = "Success text goes here.",
        **kwargs
    ):
        buttons = {
            "Exit": {"action": self.close_dialog},
            "OK": {"action": self.acknowledge_success}
        }
        
        super().__init__(
            parent=parent,
            title=title,
            message=message,
            dialog_type=self.TYPE_SUCCESS,
            buttons=buttons,
            **kwargs
        )
    
    def acknowledge_success(self):
        """Handle success acknowledgment."""
        self.button_clicked.emit("OK")
        self.accept()
    
    def close_dialog(self):
        """Handle close action."""
        self.button_clicked.emit("Exit")
        self.reject()


class InformationDialog(BaseMessageDialog):
    """
    Dialog for displaying informational messages.
    
    Shows an info icon and provides general information to users.
    """
    
    def __init__(
        self,
        parent=None,
        title: str = "Information",
        message: str = "Information goes here.",
        **kwargs
    ):
        buttons = {
            "Exit": {"action": self.close_dialog},
            "OK": {"action": self.acknowledge_info}
        }
        
        # Auto-resize for long information content
        if len(message) > 300 or message.count('\n') > 6:
            if 'size' not in kwargs:
                kwargs['size'] = (600, 450)
            if 'resizable' not in kwargs:
                kwargs['resizable'] = True
        
        super().__init__(
            parent=parent,
            title=title,
            message=message,
            dialog_type=self.TYPE_INFO,
            buttons=buttons,
            **kwargs
        )
    
    def acknowledge_info(self):
        """Handle info acknowledgment."""
        self.button_clicked.emit("OK")
        self.accept()
    
    def close_dialog(self):
        """Handle close action."""
        self.button_clicked.emit("Exit")
        self.reject()


class QuestionDialog(BaseMessageDialog):
    """
    Dialog for asking user questions requiring yes/no or similar responses.
    
    Shows a question icon and provides multiple choice options.
    """
    
    def __init__(
        self,
        parent=None,
        title: str = "Question",
        message: str = "Please select an option:",
        yes_text: str = "Yes",
        no_text: str = "No",
        yes_action: Optional[callable] = None,
        no_action: Optional[callable] = None,
        **kwargs
    ):
        buttons = {
            no_text: {"action": no_action or self.reject},
            yes_text: {"action": yes_action or self.accept}
        }
        
        super().__init__(
            parent=parent,
            title=title,
            message=message,
            dialog_type=self.TYPE_QUESTION,
            buttons=buttons,
            **kwargs
        )


class DetectionIssueDialog(BaseMessageDialog):
    """
    Dialog for displaying detection issues with expected vs actual results.
    
    Shows a warning with detailed breakdown of expected, detected, and missing items.
    Useful for droplet detection, device validation, and similar scenarios.
    """
    
    def __init__(
        self,
        parent=None,
        title: str = "Detection Issue",
        message: str = "Some items weren't detected during this step.",
        question: str = "Would you like to continue anyway or pause and review?",
        expected: Optional[str] = None,
        detected: Optional[str] = None,
        missing: Optional[str] = None,
        continue_button_text: str = "Continue Anyway",
        pause_button_text: str = "Pause and Review",
        **kwargs
    ):
        buttons = {
            continue_button_text: {"action": self.continue_anyway},
            pause_button_text: {"action": self.pause_and_review}
        }
        
        # Set default size for detection issue dialogs to be larger
        if 'size' not in kwargs:
            kwargs['size'] = (600, 450)  # Larger default size for detection dialogs
        
        super().__init__(
            parent=parent,
            title=title,
            message=message,  # Just the message, no question yet
            dialog_type=self.TYPE_WARNING,
            buttons=buttons,
            **kwargs
        )
        
        # Add detection details if provided
        if expected is not None or detected is not None or missing is not None:
            self._add_detection_details(expected, detected, missing)
        
        # Add question after the details
        self._add_question(question)
    
    def _add_detection_details(self, expected: Optional[str], detected: Optional[str], missing: Optional[str]):
        """Add detailed breakdown of detection results using the same method as error details."""
        # Build plain text with bold categories using simple formatting
        details_text = ""
        
        if expected is not None:
            details_text += f"**Expected:**\t{expected}\n"
        
        if detected is not None:
            details_text += f"**Detected:**\t{detected}\n"
        
        if missing is not None:
            details_text += f"**Missing:**\t{missing}"
        
        if details_text:
            # Use the same method that error details uses - this gives us the nice tall, scrollable section
            self.add_details_with_copy(details_text.strip(), "Detection Results:")
    
    def _add_question(self, question: str):
        """Add question text after the details."""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtGui import QFont
        from PySide6.QtCore import Qt
        
        question_label = QLabel(question)
        question_font = QFont(self.text_font_family)
        question_font.setPointSize(11)
        question_font.setWeight(QFont.Weight.Medium)
        question_label.setFont(question_font)
        question_label.setStyleSheet(f"color: {self.TEXT_COLOR}; margin-top: 15px;")
        question_label.setWordWrap(True)
        question_label.setAlignment(Qt.AlignCenter)
        
        # Add to dialog
        self.additional_content_layout.addWidget(question_label)
    

    def continue_anyway(self):
        """Handle continue anyway action."""
        self.button_clicked.emit("Continue Anyway")
        self.close_with_result(self.RESULT_CONTINUE)
    
    def pause_and_review(self):
        """Handle pause and review action."""
        self.button_clicked.emit("Pause and Review")
        self.close_with_result(self.RESULT_PAUSE)  # Using PAUSE for pause and review action


class CustomActionDialog(BaseMessageDialog):
    """
    Dialog with custom action buttons for specific workflows.
    
    Allows for completely custom button configurations and actions.
    """
    
    def __init__(
        self,
        parent=None,
        title: str = "Action Required",
        message: str = "Please select an action:",
        custom_buttons: Optional[Dict[str, Any]] = None,
        dialog_type: str = BaseMessageDialog.TYPE_INFO,
        **kwargs
    ):
        super().__init__(
            parent=parent,
            title=title,
            message=message,
            dialog_type=dialog_type,
            buttons=custom_buttons or {"OK": {"action": self.accept}},
            **kwargs
        )


# Convenience functions for quick dialog creation
def show_unsaved_changes(parent=None, **kwargs) -> int:
    """Show an unsaved changes dialog."""
    return UnsavedChangesDialog(parent=parent, **kwargs).show_dialog()


def show_error_alert(parent=None, message: str = "",
                      error_details: Optional[str] = None,
                      save_button_text: str = "Save", exit_button_text: str = "Exit",
                      **kwargs) -> int:
    """Show an error alert dialog with customizable button text."""
    dialog = ErrorAlertDialog(
        parent=parent, message=message,
        error_details=error_details, **kwargs
    )
    
    # Customize button text if different from defaults
    if save_button_text != "Save":
        dialog.set_button_text("Save", save_button_text)
    if exit_button_text != "Exit":
        dialog.set_button_text("Exit", exit_button_text)
    
    return dialog.show_dialog()


def show_success(parent=None, message: str = "", 
                 save_button_text: str = "OK", exit_button_text: str = "Exit",
                 **kwargs) -> int:
    """Show a success dialog with customizable button text."""
    dialog = SuccessDialog(parent=parent, message=message, **kwargs)
    
    # Customize button text if different from defaults
    if save_button_text != "OK":
        dialog.set_button_text("OK", save_button_text)
    if exit_button_text != "Exit":
        dialog.set_button_text("Exit", exit_button_text)
    
    return dialog.show_dialog()


def show_information(parent=None, message: str = "",
                     ok_button_text: str = "OK", exit_button_text: str = "Exit",
                     **kwargs) -> int:
    """Show an information dialog with customizable button text."""
    dialog = InformationDialog(parent=parent, message=message, **kwargs)
    
    # Customize button text if different from defaults
    if ok_button_text != "OK":
        dialog.set_button_text("OK", ok_button_text)
    if exit_button_text != "Exit":
        dialog.set_button_text("Exit", exit_button_text)
    
    return dialog.show_dialog()


def show_question(parent=None, message: str = "",
                  yes_text: str = "Yes", no_text: str = "No",
                  **kwargs) -> int:
    """Show a question dialog."""
    return QuestionDialog(
        parent=parent,
        message=message,
        yes_text=yes_text,
        no_text=no_text,
        **kwargs
    ).show_dialog()


def show_detection_issue(
    parent=None, 
    message: str = "",
    expected: Optional[str] = None,
    detected: Optional[str] = None, 
    missing: Optional[str] = None,
    **kwargs
) -> int:
    """Show a detection issue dialog with expected vs actual results."""
    return DetectionIssueDialog(
        parent=parent, 
        message=message,
        expected=expected,
        detected=detected,
        missing=missing,
        **kwargs
    ).show_dialog()
