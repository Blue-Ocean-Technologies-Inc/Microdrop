"""
Integration example showing how to use custom dialogs in Microdrop application.

This example demonstrates how to integrate the custom dialog system with the
existing Microdrop application and logger.
"""

from logger.logger_service import get_logger
from .logger_integration import add_dialog_handler_to_logger, DialogConfig
from .base_message_dialog import BaseMessageDialog
from .message_dialog_types import (
    show_error_alert, show_success, show_information, show_question
)


class MicrodropDialogIntegration:
    """
    Helper class to integrate custom dialogs with Microdrop application.
    
    This class provides easy methods to enable dialog functionality for
    existing Microdrop loggers and show custom dialogs.
    """
    
    def __init__(self, enable_dialogs: bool = False):
        """
        Initialize the dialog integration.
        
        Args:
            enable_dialogs: Whether to enable dialog display by default
        """
        self.dialog_handlers = {}
        self.dialogs_enabled = enable_dialogs
        
        # Setup main application logger with dialog capability
        self.setup_application_logger()
    
    def setup_application_logger(self):
        """Setup the main application logger with dialog capability."""
        logger = get_logger("microdrop.application")
        
        # Add dialog handler
        dialog_handler = add_dialog_handler_to_logger(
            logger.name, 
            show_dialogs=self.dialogs_enabled
        )
        
        # Configure dialog behavior for different levels
        dialog_handler.update_config('CRITICAL', DialogConfig(
            dialog_type=BaseMessageDialog.TYPE_ERROR,
            title="Critical Application Error",
            show_details=True,
            modal=True
        ))
        
        dialog_handler.update_config('ERROR', DialogConfig(
            dialog_type=BaseMessageDialog.TYPE_ERROR,
            title="Application Error",
            show_details=True,
            modal=True
        ))
        
        dialog_handler.update_config('WARNING', DialogConfig(
            dialog_type=BaseMessageDialog.TYPE_WARNING,
            title="Application Warning",
            show_details=False,
            modal=False,
            timeout=5000  # Auto-close after 5 seconds
        ))
        
        self.dialog_handlers['application'] = dialog_handler
    
    def setup_dropbot_logger(self):
        """Setup dropbot controller logger with dialog capability."""
        logger = get_logger("dropbot_controller")
        
        dialog_handler = add_dialog_handler_to_logger(
            logger.name,
            show_dialogs=self.dialogs_enabled
        )
        
        # Dropbot-specific configurations
        dialog_handler.update_config('CRITICAL', DialogConfig(
            dialog_type=BaseMessageDialog.TYPE_ERROR,
            title="DropBot Critical Error",
            show_details=True,
            modal=True
        ))
        
        dialog_handler.update_config('ERROR', DialogConfig(
            dialog_type=BaseMessageDialog.TYPE_ERROR,
            title="DropBot Connection Error",
            show_details=True,
            modal=True
        ))
        
        self.dialog_handlers['dropbot'] = dialog_handler
    
    def setup_device_viewer_logger(self):
        """Setup device viewer logger with dialog capability."""
        logger = get_logger("device_viewer")
        
        dialog_handler = add_dialog_handler_to_logger(
            logger.name,
            show_dialogs=self.dialogs_enabled
        )
        
        # Device viewer specific configurations
        dialog_handler.update_config('ERROR', DialogConfig(
            dialog_type=BaseMessageDialog.TYPE_ERROR,
            title="Device Viewer Error",
            show_details=False,
            modal=False,
            timeout=3000
        ))
        
        self.dialog_handlers['device_viewer'] = dialog_handler
    
    def enable_dialogs(self):
        """Enable dialog display for all configured loggers."""
        self.dialogs_enabled = True
        for handler in self.dialog_handlers.values():
            handler.enable_dialogs()
    
    def disable_dialogs(self):
        """Disable dialog display for all configured loggers."""
        self.dialogs_enabled = False
        for handler in self.dialog_handlers.values():
            handler.disable_dialogs()
    
    def show_connection_error(self, parent=None, device_name="DropBot"):
        """Show a standardized connection error dialog."""
        return show_error_alert(
            parent=parent,
            title="Device Connection Error",
            message=f"Failed to connect to {device_name}. Please check:\n"
                   f"• Device is powered on\n"
                   f"• USB cable is connected\n" 
                   f"• Device drivers are installed\n"
                   f"• No other applications are using the device",
            error_details=None
        )
    
    def show_save_success(self, parent=None, filename=""):
        """Show a standardized save success dialog."""
        message = "File saved successfully!"
        if filename:
            message = f"File '{filename}' saved successfully!"
        
        return show_success(
            parent=parent,
            title="Save Complete",
            message=message
        )
    
    def show_protocol_warning(self, parent=None):
        """Show a standardized protocol modification warning."""
        return show_question(
            parent=parent,
            title="Unsaved Protocol Changes",
            message="You have unsaved changes to the current protocol. "
                   "Save before continuing?",
            yes_text="Save",
            no_text="Discard"
        )
    
    def show_device_info(self, parent=None, device_info=None):
        """Show device information dialog."""
        if device_info is None:
            device_info = {
                'name': 'DropBot',
                'version': 'Unknown',
                'status': 'Connected'
            }
        
        message = f"Device: {device_info.get('name', 'Unknown')}\n"
        message += f"Version: {device_info.get('version', 'Unknown')}\n"
        message += f"Status: {device_info.get('status', 'Unknown')}"
        
        return show_information(
            parent=parent,
            title="Device Information",
            message=message
        )


# Global instance for easy access
_dialog_integration = None


def get_dialog_integration(enable_dialogs: bool = False):
    """
    Get the global dialog integration instance.
    
    Args:
        enable_dialogs: Whether to enable dialogs if creating new instance
        
    Returns:
        MicrodropDialogIntegration instance
    """
    global _dialog_integration
    
    if _dialog_integration is None:
        _dialog_integration = MicrodropDialogIntegration(enable_dialogs)
    
    return _dialog_integration


def enable_microdrop_dialogs():
    """Enable dialog display for all Microdrop loggers."""
    integration = get_dialog_integration()
    integration.setup_dropbot_logger()
    integration.setup_device_viewer_logger()
    integration.enable_dialogs()


def disable_microdrop_dialogs():
    """Disable dialog display for all Microdrop loggers."""
    integration = get_dialog_integration()
    integration.disable_dialogs()


# Convenience functions for common dialogs
def show_microdrop_error(parent=None, title="Error", message="", 
                        error_details=None):
    """Show a Microdrop-styled error dialog."""
    return show_error_alert(
        parent=parent,
        title=title,
        message=message,
        error_details=error_details
    )


def show_microdrop_success(parent=None, title="Success", message=""):
    """Show a Microdrop-styled success dialog."""
    return show_success(
        parent=parent,
        title=title,
        message=message
    )


def show_microdrop_info(parent=None, title="Information", message=""):
    """Show a Microdrop-styled information dialog."""
    return show_information(
        parent=parent,
        title=title,
        message=message
    )


def show_microdrop_question(parent=None, title="Question", message="",
                           yes_text="Yes", no_text="No"):
    """Show a Microdrop-styled question dialog."""
    return show_question(
        parent=parent,
        title=title,
        message=message,
        yes_text=yes_text,
        no_text=no_text
    )


# Example usage in Microdrop application
def example_usage():
    """Example of how to use the dialog integration in Microdrop."""
    
    # Enable dialogs for the application
    enable_microdrop_dialogs()
    
    # Now any logger can trigger dialogs
    logger = get_logger("microdrop.example")
    
    # This will show a dialog because dialogs are enabled
    logger.error("Example error message", extra={'show_dialog': True})
    
    # Show specific dialogs
    integration = get_dialog_integration()
    integration.show_connection_error()
    integration.show_save_success(filename="protocol.json")
    integration.show_device_info({
        'name': 'DropBot v3.1',
        'version': '3.1.2',
        'status': 'Connected'
    })
    
    # Disable dialogs when not needed
    disable_microdrop_dialogs()


if __name__ == "__main__":
    # Run example
    example_usage()
