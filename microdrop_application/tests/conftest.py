"""Shared fixtures for microdrop_application tests."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication so Qt dialog tests can construct
    widgets without crashing (mirrors pluggable_protocol_tree's)."""
    from pyface.qt.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # Don't quit — lets subsequent test modules reuse the QApplication.
