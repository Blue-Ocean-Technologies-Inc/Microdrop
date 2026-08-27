# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""
Custom messaging dialog system for Microdrop application.

This module provides a comprehensive dialog system that integrates with the application's
logging framework to display various types of messages with consistent styling.
"""

from .base_message_dialog import BaseMessageDialog
from .message_dialog_types import (
    WarningAlertDialog,
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
    show_detection_issue,
)
from .logger_integration import LoggerDialogHandler, DialogLogger

__all__ = [
    "BaseMessageDialog",
    "WarningAlertDialog",
    "ErrorAlertDialog",
    "SuccessDialog",
    "InformationDialog",
    "QuestionDialog",
    "DetectionIssueDialog",
    "CustomActionDialog",
    "LoggerDialogHandler",
    "DialogLogger",
    "show_unsaved_changes",
    "show_error_alert",
    "show_success",
    "show_information",
    "show_question",
    "show_detection_issue",
]
