#!/usr/bin/env python3
"""
Test script to demonstrate the dropbot disconnection warning functionality.

This script shows how the warning dialog works when trying to send requests
while the dropbot is disconnected. The connection status is now tracked via
message traits (connected_message and disconnected_message) rather than
service dependencies.
"""

import sys
from PySide6.QtWidgets import QApplication
from dropbot_status.dialogs import DropbotDisconnectedWarningDialog


def test_warning_dialog():
    """Test the warning dialog functionality."""
    app = QApplication(sys.argv)

    # Test different request types
    request_types = ["voltage change", "frequency change", "realtime mode change"]

    for request_type in request_types:
        print(f"\nTesting warning dialog for: {request_type}")

        dialog = DropbotDisconnectedWarningDialog(request_type=request_type)

        result = dialog.show_dialog()

        if result == dialog.Accepted:
            print(f"User chose to proceed with {request_type}")
        else:
            print(f"User cancelled {request_type}")

    app.quit()


if __name__ == "__main__":
    test_warning_dialog()
