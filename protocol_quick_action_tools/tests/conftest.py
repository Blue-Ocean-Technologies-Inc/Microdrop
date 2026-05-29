"""Shared fixtures for protocol_quick_action_tools tests."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication so Qt widget tests can construct
    QDialog + child widgets without crashing."""
    from pyface.qt.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # Don't quit — lets subsequent test modules reuse the same QApplication.
