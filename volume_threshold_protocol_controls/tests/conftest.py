"""Session-scoped qapp fixture. Matches the per-plugin pattern used
in peripheral_protocol_controls / dropbot_protocol_controls /
protocol_quick_action_tools."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    from pyface.qt.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
