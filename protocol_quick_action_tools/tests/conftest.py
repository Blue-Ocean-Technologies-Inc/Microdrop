# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

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
