"""
Pyface-compatible dialog wrapper using styled BaseMessageDialog.

This module provides Pyface-compatible dialog functions that use the custom
styled BaseMessageDialog system, allowing existing Pyface code to use
the application's modern dialog styling without code changes.

Usage:
    # Replace this:
    from pyface.api import confirm, YES, NO

    # With this:
    from microdrop_application.dialogs.pyface_wrapper import confirm, YES, NO

    # Usage remains identical:
    if confirm(parent, "Continue?", title="Confirm") == YES:
        do_something()
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QWidget

# Re-export Pyface constants for compatibility
try:
    from pyface.api import CANCEL, NO, OK, YES, FileDialog

    PYFACE_FILE_OK = OK
except ImportError:
    # Fallback if pyface is not available
    YES = 1
    NO = 0
    OK = 1
    CANCEL = 0
    FileDialog = None
    PYFACE_FILE_OK = OK

from .base_message_dialog import BaseMessageDialog
from .message_dialog_types import (
    ErrorAlertDialog,
    InformationDialog,
    SuccessDialog,
    WarningAlertDialog,
)


def _prepare_dialog(
    dialog_factory,
    parent: Optional[QWidget],
    title: str,
    message: str,
    detail: Optional[str] = None,
    detail_visible_lines: Optional[int] = None,
    informative: Optional[str] = None,
    text_format: Optional[str] = None,
    detail_collapsible: Optional[bool] = True,
    modal: Optional[bool] =True,
    **kwargs
) -> BaseMessageDialog:
    """
    Helper to create and prepare a dialog with common logic for
    informative text (HTML) and details.
    """
    # Use informative as main message if provided, otherwise use message
    main_message = informative if informative else message
    is_html = (text_format == "auto" and informative is not None) or (informative is not None)

    # When both informative and detail are provided, disable scrolling for
    # main message so informative stays in non-scrollable area
    disable_main_scrolling = informative is not None and detail is not None

    # Create the dialog
    dialog = dialog_factory(parent=parent, title=title, message=main_message, disable_main_scrolling=disable_main_scrolling, **kwargs)

    if not modal:
        dialog.setWindowModality(Qt.NonModal)

    # Set message as HTML if informative was provided
    if is_html:
        dialog.set_message(main_message, is_html=True)

    # Add detail in collapsible section if provided
    if detail:
        dialog.add_details_with_copy(detail, "Details:", collapsible=detail_collapsible, visible_lines=detail_visible_lines)

    return dialog


def confirm(
    parent: Optional[QWidget] = None,
    message: str = "",
    title: str = "Confirm",
    cancel: bool = False,
    yes_label: str = "Yes",
    no_label: str = "No",
    cancel_label: str = "Cancel",
    detail: Optional[str] = None,
    detail_visible_lines: Optional[int] = None,
    informative: Optional[str] = None,
    text_format: Optional[str] = None,
    **kwargs
) -> int:
    """
    Pyface-compatible confirm dialog using styled BaseMessageDialog.
    """
    # Build buttons for a styled question dialog
    dialog_ref = [None]  # Use list for mutable closure reference

    def close_result(result):
        if dialog_ref[0] is not None:
            dialog_ref[0].close_with_result(result)

    buttons = {
        no_label: {"action": lambda: close_result(BaseMessageDialog.RESULT_NO)},
        yes_label: {"action": lambda: close_result(BaseMessageDialog.RESULT_YES)},
    }
    if cancel:
        buttons[cancel_label] = {"action": lambda: close_result(BaseMessageDialog.RESULT_CANCEL)}

    # Factory function to create BaseMessageDialog
    def create_dialog(**opts):
        return BaseMessageDialog(dialog_type=BaseMessageDialog.TYPE_QUESTION, buttons=buttons, **opts)

    dialog = _prepare_dialog(create_dialog, parent, title, message, detail, detail_visible_lines, informative, text_format, **kwargs)
    dialog_ref[0] = dialog

    # Show dialog and get result
    result = dialog.exec()

    # Map QDialog results to Pyface constants
    if result in (BaseMessageDialog.RESULT_OK, BaseMessageDialog.RESULT_YES):
        return YES
    if result == BaseMessageDialog.RESULT_NO:
        return NO
    return CANCEL


def information(
    parent: Optional[QWidget] = None,
    message: str = "",
    title: str = "Information",
    cancel: bool = True,
    detail: Optional[str] = None,
    detail_visible_lines: Optional[int] = None,
    informative: Optional[str] = None,
    text_format: Optional[str] = None,
    detail_collapsible: Optional[bool] = True,
    timeout: Optional[int] = 0,
    **kwargs
) -> int:
    """
    Pyface-compatible information dialog using styled BaseMessageDialog.
    """

    def create_dialog(**opts):
        return InformationDialog(exit=cancel, **opts)

    dialog = _prepare_dialog(create_dialog, parent, title, message, detail, detail_visible_lines, informative, text_format, detail_collapsible, **kwargs)

    result = dialog.exec()

    if timeout: # temp message
        QTimer.singleShot(timeout, dialog.close)

    else:
        if result == BaseMessageDialog.RESULT_OK:
            return OK

        return CANCEL


def success(
    parent: Optional[QWidget] = None,
    message: str = "",
    title: str = "Success",
    cancel: bool = False,
    detail: Optional[str] = None,
    detail_visible_lines: Optional[int] = None,
    informative: Optional[str] = None,
    text_format: Optional[str] = None,
    timeout: Optional[int] = 0,
    **kwargs
):
    """
    Pyface-compatible success dialog using styled BaseMessageDialog.
    """

    def create_dialog(**opts):
        return SuccessDialog(exit=cancel, **opts)

    dialog = _prepare_dialog(create_dialog, parent, title, message, detail, detail_visible_lines, informative, text_format, **kwargs)

    if timeout: # temp message
        dialog.show()
        QTimer.singleShot(timeout, dialog.close)

    else:
        result = dialog.exec()
        if result == BaseMessageDialog.RESULT_OK:
            return OK

        return CANCEL


def warning(
    parent: Optional[QWidget] = None,
    message: str = "",
    title: str = "Warning",
    cancel: bool = True,
    detail: Optional[str] = None,
    detail_visible_lines: Optional[int] = None,
    informative: Optional[str] = None,
    text_format: Optional[str] = None,
    **kwargs
) -> int:
    """
    Pyface-compatible warning dialog using styled BaseMessageDialog.
    """

    def create_dialog(**opts):
        return WarningAlertDialog(exit=cancel, **opts)

    dialog = _prepare_dialog(create_dialog, parent, title, message, detail, detail_visible_lines, informative, text_format, **kwargs)

    # Override default buttons to match Pyface warning dialog
    dialog.set_button_text("Discard Changes", "OK")
    dialog.set_button_text("Save Changes", "Cancel")

    result = dialog.exec()

    # Map to Pyface OK constant
    if result == BaseMessageDialog.RESULT_OK:
        return OK
    return CANCEL


def error(
    parent: Optional[QWidget] = None,
    message: str = "",
    title: str = "Error",
    detail: Optional[str] = None,
    detail_visible_lines: Optional[int] = None,
    informative: Optional[str] = None,
    text_format: Optional[str] = None,
    **kwargs
) -> int:
    """
    Pyface-compatible error dialog using styled BaseMessageDialog.
    """

    def create_dialog(**opts):
        return ErrorAlertDialog(error_details=None, **opts)  # Detail is handled by _prepare_dialog

    dialog = _prepare_dialog(create_dialog, parent, title, message, detail, detail_visible_lines, informative, text_format, **kwargs)

    # Override default buttons to match Pyface error dialog
    dialog.set_button_text("Save", "OK")

    result = dialog.exec()

    # Map to Pyface OK constant
    if result == BaseMessageDialog.RESULT_OK:
        return OK
    return CANCEL


# Optional: FileDialog wrapper if needed
def file_dialog(parent: Optional[QWidget] = None, action: str = "open", default_path: str = "", wildcard: str = "All files (*.*)", **kwargs):
    """
    Pyface-compatible file dialog wrapper.

    Note: This is a placeholder. For full file dialog functionality,
    you may want to use PySide6.QtWidgets.QFileDialog directly or
    keep using pyface.api.FileDialog.

    Args:
        parent: Parent widget
        action: "open" or "save"
        default_path: Default file path
        wildcard: File filter wildcard
        **kwargs: Additional arguments

    Returns:
        File path if selected, None otherwise
    """
    # For now, delegate to Pyface's FileDialog when available.
    # In the future, could create a styled file dialog.
    if FileDialog is not None:
        if action == "open":
            dialog = FileDialog(parent=parent, default_path=default_path, wildcard=wildcard)
        else:
            dialog = FileDialog(
                parent=parent,
                default_path=default_path,
                wildcard=wildcard,
                action="save",
            )
        if dialog.open() == PYFACE_FILE_OK:
            return dialog.path
        return None

    # Fallback to PySide6 QFileDialog
    if action == "open":
        path, _ = QFileDialog.getOpenFileName(parent, "Open File", default_path, wildcard)
    else:
        path, _ = QFileDialog.getSaveFileName(parent, "Save File", default_path, wildcard)
    return path if path else None


# Export all for easy import
__all__ = [
    "confirm",
    "information",
    "success",
    "warning",
    "error",
    "file_dialog",
    "YES",
    "NO",
    "OK",
    "CANCEL",
]
