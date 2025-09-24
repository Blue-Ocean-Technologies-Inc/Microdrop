"""
Custom messaging dialog system for Microdrop application.

This module provides a comprehensive dialog system that integrates with the application's
logging framework to display various types of messages with consistent styling.
"""

from .base_message_dialog import BaseMessageDialog
from .message_dialog_types import (
    UnsavedChangesDialog,
    ErrorAlertDialog,
    SuccessDialog,
    InformationDialog,
    QuestionDialog,
    DetectionIssueDialog,
    CustomActionDialog,
    show_unsaved_changes,
    show_error_alert,
    show_success,
    show_information,
    show_question,
    show_detection_issue
)
from .logger_integration import LoggerDialogHandler, DialogLogger

__all__ = [
    'BaseMessageDialog',
    'UnsavedChangesDialog',
    'ErrorAlertDialog',
    'SuccessDialog',
    'InformationDialog',
    'QuestionDialog',
    'DetectionIssueDialog',
    'CustomActionDialog',
    'LoggerDialogHandler',
    'DialogLogger',
    'show_unsaved_changes',
    'show_error_alert',
    'show_success',
    'show_information',
    'show_question',
    'show_detection_issue'
]
