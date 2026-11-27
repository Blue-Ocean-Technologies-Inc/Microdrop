# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fixtures shared by the portable_dropbot_controller tests."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils import realtime_mode_mixin


@pytest.fixture(autouse=True)
def realtime_mode_key_store(monkeypatch):
    """Stand in for the app globals the backend's realtime mode writes to."""
    store = {}
    monkeypatch.setattr(realtime_mode_mixin, "app_globals", store)

    return store
