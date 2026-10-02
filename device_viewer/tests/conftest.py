# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import sys
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest


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
    with patch.dict(
        "sys.modules",
        {
            "microdrop_utils.redis_manager": MagicMock(
                RedisManager=MagicMock(return_value=fake_redis_manager)
            ),
        },
    ):
        yield


@pytest.fixture(autouse=True)
def _isolate_app_globals_writes(monkeypatch):
    """Route the device models' app-globals writes to plain dicts.

    Test modules import the models at collection time — before the session
    mock above exists — so their ``app_globals`` is the live Redis hash. A
    model loading a device SVG then published the test preferences'
    repo dir (``Documents/Enthought/Devices``) over a running app's,
    which is what the image viewer's device dropdown read back. With no
    Redis server, every write instead costs a ~2 s refused connect
    (``Electrodes`` writes its area map on each device load), which
    pushed the zone tests past any reasonable timeout.
    """
    from device_viewer.models import calibration, electrodes, main_model, zones

    for module in (calibration, electrodes, main_model, zones):
        monkeypatch.setattr(module, "app_globals", {})
