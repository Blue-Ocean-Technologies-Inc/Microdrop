"""Shared fixtures for pluggable_protocol_tree tests."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication so Qt widget tests can construct
    QMainWindow + child widgets without crashing."""
    from pyface.qt.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # Don't quit — pytest-qt doesn't either; lets subsequent test
    # modules reuse the same QApplication.
