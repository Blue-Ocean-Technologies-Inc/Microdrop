# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import sys

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(scope="session", autouse=True)
def _mock_redis_for_dock_pane_import():
    """Mock Redis at sys.modules level so importing device_view_dock_pane
    (which calls is_advanced_mode() at class-definition time) does not
    try to connect to a real broker. Session-scoped so the patch is
    active for the whole pytest run."""
    fake_redis_manager = MagicMock()
    fake_redis_manager.get.return_value = False
    # Pre-delete the to-be-mocked modules BEFORE entering patch.dict
    # so that patch.dict's exit restores them to "absent" (their
    # original not-yet-imported state).
    for mod in list(sys.modules.keys()):
        if "microdrop_application.menus" in mod or "app_globals" in mod:
            del sys.modules[mod]
    with patch.dict("sys.modules", {
        "microdrop_utils.redis_manager": MagicMock(
            RedisManager=MagicMock(return_value=fake_redis_manager)
        ),
    }):
        yield
