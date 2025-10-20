# Custom Messaging Dialog System

A comprehensive dialog system for the Microdrop application that provides consistent, styled messaging windows with logger integration.

## Overview

This dialog system provides:
- **Consistent styling** matching the application's theme
- **Multiple dialog types** for different scenarios (error, success, warning, info, question)
- **Logger integration** with configurable popup behavior
- **Dark/light mode support** 
- **Customizable actions** and buttons
- **Thread-safe operation** for use with async operations

## Architecture

### Core Components

- **`BaseMessageDialog`** - Template class providing common functionality
- **`message_dialog_types.py`** - Specific dialog implementations 
- **`logger_integration.py`** - Logger handler for triggering dialogs
- **`examples.py`** - Usage examples and test widget

### Dialog Types

1. **`UnsavedChangesDialog`** - For unsaved changes warnings
2. **`ErrorAlertDialog`** - For error messages with details
3. **`SuccessDialog`** - For success confirmations
4. **`InformationDialog`** - For general information
5. **`QuestionDialog`** - For yes/no questions
6. **`CustomActionDialog`** - For custom button configurations

## Usage

### Basic Dialog Usage

```python
from microdrop_application.dialogs import show_information, show_error_alert

# Simple information dialog
result = show_information(
    parent=main_window,
    title="Welcome",
    message="Welcome to Microdrop Next Gen!"
)

# Error dialog with details
result = show_error_alert(
    parent=main_window,
    title="Connection Error", 
    message="Failed to connect to device",
    error_details="ConnectionError: Device not found"
)
```

### Logger Integration

```python
from microdrop_application.dialogs import DialogLogger, enable_dialog_logging

# Method 1: Create dialog-enabled logger
dialog_logger = DialogLogger("my.module", show_dialogs=True)
dialog_logger.error_with_dialog("This error will show a popup!")

# Method 2: Enable dialogs for existing logger
enable_dialog_logging("microdrop.controller")
logger = logging.getLogger("microdrop.controller")
logger.error("This will show a dialog", extra={'show_dialog': True})
```

### Custom Dialog Configuration

```python
from microdrop_application.dialogs import ErrorAlertDialog

dialog = ErrorAlertDialog(
    parent=main_window,
    title="Critical Error",
    message="System error occurred",
    size=(500, 300),
    modal=True
)

# Customize buttons
save_button = dialog.get_button("Save")
save_button.setText("Restart")
save_button.clicked.connect(restart_system)

result = dialog.show_dialog()
```

## Integration with Microdrop Application

### Adding to Existing Logger

```python
from logger.logger_service import get_logger
from microdrop_application.dialogs import add_dialog_handler_to_logger

# Add dialog capability to existing Microdrop logger
logger = get_logger(__name__)
dialog_handler = add_dialog_handler_to_logger(logger.name, show_dialogs=True)

# Now logger can show dialogs
logger.critical("Critical error!", extra={'show_dialog': True})
```

### Application-wide Integration

```python
from microdrop_application.dialogs import enable_dialog_logging

# Enable dialog logging globally
enable_dialog_logging()

# All WARNING+ level logs can now potentially show dialogs
# Controlled by logger configuration and message content
```

## Styling and Theme

The dialog system automatically:
- Uses application fonts (Inter for text, Material Symbols for icons)
- Adapts to dark/light mode
- Applies consistent color scheme from `microdrop_style/colors.py`
- Includes subtle drop shadows and rounded corners
- Follows Material Design principles

## Configuration

### Dialog Types and Colors

- **Info**: Blue (`INFO_COLOR`)
- **Success**: Green (`SUCCESS_COLOR`) 
- **Warning**: Orange (`WARNING_COLOR`)
- **Error**: Red (`ERROR_COLOR`)
- **Question**: Primary color (`PRIMARY_COLOR`)

### Logger Integration Settings

```python
from microdrop_application.dialogs import DialogConfig

# Custom configuration for specific log levels
config = DialogConfig(
    dialog_type=BaseMessageDialog.TYPE_ERROR,
    title="Custom Error",
    show_details=True,
    modal=True,
    timeout=5000  # Auto-close after 5 seconds
)

dialog_handler.update_config('ERROR', config)
```

## Thread Safety

The dialog system is designed to be thread-safe:
- Uses Qt signals for cross-thread communication
- Dialogs always display in the main GUI thread
- Safe to call from background workers and async operations

## Examples

See `examples.py` for comprehensive usage examples, including:
- Basic dialog demonstrations
- Custom styling and configuration
- Logger integration patterns
- Test widget for development

## Testing

Run the test widget:

```python
from microdrop_application.dialogs.examples import run_dialog_test

# Shows test widget with buttons for all dialog types
test_widget = run_dialog_test()
```

## Best Practices

1. **Use appropriate dialog types** for different scenarios
2. **Provide clear, actionable messages** 
3. **Include error details** for technical errors
4. **Use logger integration** for automatic popup behavior
5. **Test with both light and dark themes**
6. **Consider modal vs non-modal** based on urgency
7. **Implement auto-close timeouts** for non-critical messages

## Future Enhancements

- Toast notifications for non-intrusive messages
- Dialog queuing system for multiple simultaneous messages  
- Custom animations and transitions
- Integration with application settings for user preferences
- Accessibility improvements (screen reader support, keyboard navigation)
