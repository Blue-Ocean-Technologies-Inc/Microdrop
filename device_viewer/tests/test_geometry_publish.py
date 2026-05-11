"""Tests for DV-side DEVICE_VIEWER_GEOMETRY_CHANGED publishing."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from device_viewer.consts import DEVICE_VIEWER_GEOMETRY_CHANGED
from device_viewer.models.messages import GeometryChangedMessage


@pytest.fixture(scope="session", autouse=True)
def _mock_redis_for_dock_pane_import():
    """Patch the Redis-backed app_globals so importing device_view_dock_pane
    doesn't fail when no Redis server is running."""
    # Stub out the redis_manager so that the module-level is_advanced_mode()
    # call inside microdrop_application.menus does not attempt to connect.
    fake_redis_manager = MagicMock()
    fake_redis_manager.get.return_value = False
    fake_redis_manager.__getitem__ = MagicMock(return_value=None)

    with patch.dict(
        "sys.modules",
        {
            "microdrop_utils.redis_manager": MagicMock(
                RedisManager=MagicMock(return_value=fake_redis_manager)
            ),
        },
    ):
        # Force re-import of modules that cached redis at import time.
        for mod in list(sys.modules.keys()):
            if "microdrop_application.menus" in mod or "app_globals" in mod:
                del sys.modules[mod]
        yield


@pytest.fixture
def fake_dock_pane():
    """A minimal stand-in for DeviceViewDockPane carrying just the
    attributes the helper touches."""

    class _Electrode:
        def __init__(self, channel):
            self.channel = channel

    pane = MagicMock()
    pane._last_published_id_to_channel = None
    pane.model.electrodes.electrodes = {
        "e00": _Electrode(0),
        "e01": _Electrode(1),
        "e02": _Electrode(None),
    }
    return pane


def test_publishes_on_first_call(fake_dock_pane):
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewerDockPane,
    )
    with patch(
        "device_viewer.views.device_view_dock_pane.publish_message"
    ) as send:
        DeviceViewerDockPane._publish_geometry_if_changed(fake_dock_pane)

    send.send.assert_called_once()
    args, kwargs = send.send.call_args
    assert kwargs["topic"] == DEVICE_VIEWER_GEOMETRY_CHANGED
    msg = GeometryChangedMessage.deserialize(kwargs["message"])
    assert msg.id_to_channel == {"e00": 0, "e01": 1, "e02": None}


def test_no_republish_when_unchanged(fake_dock_pane):
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewerDockPane,
    )
    with patch(
        "device_viewer.views.device_view_dock_pane.publish_message"
    ) as send:
        DeviceViewerDockPane._publish_geometry_if_changed(fake_dock_pane)
        DeviceViewerDockPane._publish_geometry_if_changed(fake_dock_pane)
    assert send.send.call_count == 1


def test_republishes_when_mapping_changes(fake_dock_pane):
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewerDockPane,
    )
    with patch(
        "device_viewer.views.device_view_dock_pane.publish_message"
    ) as send:
        DeviceViewerDockPane._publish_geometry_if_changed(fake_dock_pane)
        # Simulate chip insert: mapping changes
        fake_dock_pane.model.electrodes.electrodes["e00"].channel = 5
        DeviceViewerDockPane._publish_geometry_if_changed(fake_dock_pane)
    assert send.send.call_count == 2
