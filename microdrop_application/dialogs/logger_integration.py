"""
Logger integration for custom messaging dialogs.

This module provides integration between the application's logging system and
the custom dialog system, allowing logs to trigger popup dialogs when specific
flags are set.
"""

import logging
import threading
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication

from .message_dialog_types import (
    ErrorAlertDialog, SuccessDialog, InformationDialog,
    UnsavedChangesDialog
)
from .base_message_dialog import BaseMessageDialog


@dataclass
class DialogConfig:
    """Configuration for dialog display."""
    dialog_type: str
    title: str = ""
    show_details: bool = True
    modal: bool = True
    timeout: Optional[int] = None  # Auto-close after N seconds
    custom_buttons: Optional[Dict[str, Any]] = None


class LoggerDialogHandler(logging.Handler, QObject):
    """
    Custom logging handler that can display dialogs for specific
    log messages.
    
    This handler integrates with the application's logger to show
    popup dialogs
    when certain conditions are met (specific log levels, flags,
    or patterns).
    """
    
    # Qt signals for thread-safe dialog display
    show_dialog_signal = Signal(str, str, str, dict)
    
    def __init__(
        self, 
        level=logging.NOTSET,
        show_dialogs: bool = False,
        dialog_configs: Optional[Dict[str, DialogConfig]] = None
    ):
        logging.Handler.__init__(self, level)
        QObject.__init__(self)
        
        self.show_dialogs = show_dialogs
        self.dialog_configs = dialog_configs or self._get_default_configs()
        self.current_dialogs: Set[str] = set()
        self.dialog_queue = []
        self._lock = threading.Lock()
        
        # Connect signal to dialog display method
        self.show_dialog_signal.connect(self._display_dialog_from_signal)
        
        # Timer for processing dialog queue
        self.queue_timer = QTimer()
        self.queue_timer.setSingleShot(False)
        self.queue_timer.timeout.connect(self._process_dialog_queue)
        self.queue_timer.start(100)
    
    def _get_default_configs(self) -> Dict[str, DialogConfig]:
        """Get default dialog configurations for different log levels."""
        return {
            'CRITICAL': DialogConfig(
                dialog_type=BaseMessageDialog.TYPE_ERROR,
                title="Critical Error",
                show_details=True,
                modal=True
            ),
            'ERROR': DialogConfig(
                dialog_type=BaseMessageDialog.TYPE_ERROR,
                title="Error",
                show_details=True,
                modal=True
            ),
            'WARNING': DialogConfig(
                dialog_type=BaseMessageDialog.TYPE_WARNING,
                title="Warning",
                show_details=False,
                modal=False
            ),
            'INFO': DialogConfig(
                dialog_type=BaseMessageDialog.TYPE_INFO,
                title="Information",
                show_details=False,
                modal=False,
                timeout=5000
            ),
            'SUCCESS': DialogConfig(
                dialog_type=BaseMessageDialog.TYPE_SUCCESS,
                title="Success",
                show_details=False,
                modal=False,
                timeout=3000
            )
        }
    
    def emit(self, record: logging.LogRecord):
        """
        Handle a log record and potentially show a dialog.
        
        Args:
            record: The log record to process
        """
        if not self.show_dialogs:
            return
        
        # Check if this record should trigger a dialog
        if self._should_show_dialog(record):
            message = self.format(record)
            level_name = record.levelname
            config = self.dialog_configs.get(level_name, self.dialog_configs.get('INFO'))
            
            # Create dialog config dict for signal
            config_dict = {
                'dialog_type': config.dialog_type,
                'title': config.title or f"{level_name}: {record.name}",
                'show_details': config.show_details,
                'modal': config.modal,
                'timeout': config.timeout,
                'custom_buttons': config.custom_buttons
            }
            
            # Add error details if available
            if hasattr(record, 'exc_info') and record.exc_info:
                config_dict['error_details'] = self._format_exception(record.exc_info)
            
            # Emit signal to show dialog (thread-safe)
            self.show_dialog_signal.emit(level_name, message, record.name, config_dict)
    
    def _should_show_dialog(self, record: logging.LogRecord) -> bool:
        """
        Determine if a log record should trigger a dialog.
        
        Args:
            record: The log record to check
            
        Returns:
            True if a dialog should be shown
        """
        # Check log level
        if record.levelno < logging.WARNING:
            return False
        
        # Check for dialog flag in record
        if hasattr(record, 'show_dialog') and record.show_dialog:
            return True
        
        # Check for specific patterns in message
        if hasattr(record, 'msg'):
            msg = str(record.msg).lower()
            # Show dialogs for critical operations
            if any(keyword in msg for keyword in
                   ['critical', 'fatal', 'emergency', 'panic']):
                return True
            
            # Show dialogs for user-facing errors
            if any(keyword in msg for keyword in
                   ['user error', 'input error', 'validation error']):
                return True
        
        # Default behavior for WARNING and above
        return record.levelno >= logging.WARNING
    
    def _display_dialog_from_signal(self, level: str, message: str,
                                     logger_name: str,
                                     config: Dict[str, Any]):
        """
        Display dialog from Qt signal (runs in main thread).
        
        Args:
            level: Log level name
            message: Message to display
            logger_name: Name of logger that emitted the record
            config: Dialog configuration dictionary
        """
        with self._lock:
            # Avoid duplicate dialogs
            dialog_key = f"{level}:{hash(message)}"
            if dialog_key in self.current_dialogs:
                return
            
            self.current_dialogs.add(dialog_key)
        
        try:
            # Get application main window as parent
            app = QApplication.instance()
            parent = None
            if app and app.activeWindow():
                parent = app.activeWindow()
            
            # Create appropriate dialog based on type
            dialog_type = config.get('dialog_type', BaseMessageDialog.TYPE_INFO)
            title = config.get('title', level)
            modal = config.get('modal', True)
            
            dialog = None
            
            if dialog_type == BaseMessageDialog.TYPE_ERROR:
                error_details = config.get('error_details')
                dialog = ErrorAlertDialog(
                    parent=parent,
                    title=title,
                    message=message,
                    error_details=error_details
                )
            elif dialog_type == BaseMessageDialog.TYPE_SUCCESS:
                dialog = SuccessDialog(
                    parent=parent,
                    title=title,
                    message=message
                )
            elif dialog_type == BaseMessageDialog.TYPE_WARNING:
                dialog = UnsavedChangesDialog(
                    parent=parent,
                    title=title,
                    message=message
                )
            else:  # INFO or default
                dialog = InformationDialog(
                    parent=parent,
                    title=title,
                    message=message
                )
            
            # Set modal property
            dialog.setModal(modal)
            
            # Handle auto-close timeout
            timeout = config.get('timeout')
            if timeout and timeout > 0:
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(dialog.accept)
                timer.start(timeout)
            
            # Connect dialog closed signal to cleanup
            dialog.dialog_closed.connect(
                lambda: self._cleanup_dialog(dialog_key)
            )
            
            # Show dialog
            if modal:
                dialog.exec()
            else:
                dialog.show()
                
        except Exception as e:
            # Log error but don't create infinite loop
            print(f"Error displaying dialog: {e}")
        finally:
            # Always cleanup
            with self._lock:
                self.current_dialogs.discard(dialog_key)
    
    def _cleanup_dialog(self, dialog_key: str):
        """Clean up dialog tracking."""
        with self._lock:
            self.current_dialogs.discard(dialog_key)
    
    def _process_dialog_queue(self):
        """Process queued dialogs."""
        # This can be used for more sophisticated dialog queuing
        # Currently handled by the signal mechanism
        pass
    
    def _format_exception(self, exc_info) -> str:
        """Format exception information for display."""
        import traceback
        return ''.join(traceback.format_exception(*exc_info))
    
    def enable_dialogs(self):
        """Enable dialog display for log messages."""
        self.show_dialogs = True
    
    def disable_dialogs(self):
        """Disable dialog display for log messages."""
        self.show_dialogs = False
    
    def update_config(self, level: str, config: DialogConfig):
        """Update configuration for a specific log level."""
        self.dialog_configs[level] = config


class DialogLogger:
    """
    Wrapper class to easily integrate dialog functionality with existing loggers.
    
    This class provides a simple interface to add dialog capabilities to any logger.
    """
    
    def __init__(self, logger_name: str, show_dialogs: bool = False):
        self.logger = logging.getLogger(logger_name)
        self.dialog_handler = LoggerDialogHandler(show_dialogs=show_dialogs)
        self.logger.addHandler(self.dialog_handler)
    
    def enable_dialogs(self):
        """Enable dialog display."""
        self.dialog_handler.enable_dialogs()
    
    def disable_dialogs(self):
        """Disable dialog display."""
        self.dialog_handler.disable_dialogs()
    
    def log_with_dialog(self, level: int, message: str, **kwargs):
        """Log a message with dialog display flag."""
        # Add dialog flag to extra data
        extra = kwargs.get('extra', {})
        extra['show_dialog'] = True
        kwargs['extra'] = extra
        
        self.logger.log(level, message, **kwargs)
    
    def error_with_dialog(self, message: str, **kwargs):
        """Log an error with dialog display."""
        self.log_with_dialog(logging.ERROR, message, **kwargs)
    
    def warning_with_dialog(self, message: str, **kwargs):
        """Log a warning with dialog display."""
        self.log_with_dialog(logging.WARNING, message, **kwargs)
    
    def info_with_dialog(self, message: str, **kwargs):
        """Log info with dialog display."""
        self.log_with_dialog(logging.INFO, message, **kwargs)
    
    def success_with_dialog(self, message: str, **kwargs):
        """Log a success message with dialog display."""
        # Create custom log level for success if it doesn't exist
        if not hasattr(logging, 'SUCCESS'):
            logging.addLevelName(25, 'SUCCESS')  # Between INFO(20) and WARNING(30)
        
        self.log_with_dialog(25, message, **kwargs)


# Convenience functions for global logger integration
def add_dialog_handler_to_logger(logger_name: str, show_dialogs: bool = False) -> LoggerDialogHandler:
    """
    Add a dialog handler to an existing logger.
    
    Args:
        logger_name: Name of the logger
        show_dialogs: Whether to initially show dialogs
        
    Returns:
        The dialog handler instance
    """
    logger = logging.getLogger(logger_name)
    handler = LoggerDialogHandler(show_dialogs=show_dialogs)
    logger.addHandler(handler)
    return handler


def enable_dialog_logging(logger_name: str = None):
    """
    Enable dialog logging for a specific logger or all loggers.
    
    Args:
        logger_name: Specific logger name, or None for root logger
    """
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()
    
    # Find existing dialog handlers and enable them
    for handler in logger.handlers:
        if isinstance(handler, LoggerDialogHandler):
            handler.enable_dialogs()
            return
    
    # No dialog handler found, add one
    handler = LoggerDialogHandler(show_dialogs=True)
    logger.addHandler(handler)


def disable_dialog_logging(logger_name: str = None):
    """
    Disable dialog logging for a specific logger or all loggers.
    
    Args:
        logger_name: Specific logger name, or None for root logger
    """
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()
    
    # Find existing dialog handlers and disable them
    for handler in logger.handlers:
        if isinstance(handler, LoggerDialogHandler):
            handler.disable_dialogs()
