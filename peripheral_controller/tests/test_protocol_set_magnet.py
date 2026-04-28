"""Tests for the protocol-driven magnet engage/retract handler.

The handler is symmetric to the existing UI handlers in shape but
owns the engage/retract sequence atomically — protocol-side does
one publish + one wait_for instead of two."""
import json
from unittest.mock import MagicMock, patch

from peripheral_controller.consts import (
    MAGNET_APPLIED, MIN_ZSTAGE_HEIGHT_MM,
)
from peripheral_controller.services.zstage_state_setter_service import (
    ZStageStatesSetterMixinService,
)


def _make_service():
    svc = ZStageStatesSetterMixinService()
    # Bypass the Traits Instance type check so MagicMock is accepted.
    object.__setattr__(svc, "proxy", MagicMock())
    return svc


def test_protocol_set_magnet_off_runs_retract_sequence():
    """{'on': false, ...} -> proxy.zstage.down() then 0.3s sleep then
    proxy.zstage.home(). Verify exact call order."""
    svc = _make_service()
    published = []
    with patch(
        "peripheral_controller.services.zstage_state_setter_service.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ), patch(
        "peripheral_controller.services.zstage_state_setter_service.time.sleep",
    ) as mock_sleep:
        svc.on_protocol_set_magnet_request(json.dumps({
            "on": False, "height_mm": 0.0,
        }))

    # Order of calls on the proxy.zstage:
    method_names = [c[0] for c in svc.proxy.zstage.method_calls]
    assert method_names == ["down", "home"]
    mock_sleep.assert_called_once_with(0.3)
    assert published == [{"topic": MAGNET_APPLIED, "message": "0"}]


def test_protocol_set_magnet_on_with_specific_height():
    """{'on': true, 'height_mm': 12.5} -> proxy.zstage.position = 12.5;
    publishes MAGNET_APPLIED with payload '1'."""
    svc = _make_service()
    published = []

    def _capture_publish(*args, **kwargs):
        # publish_position_update calls publish_message with positional args;
        # on_protocol_set_magnet_request calls it with keyword args.
        # Only record calls made with keyword args (i.e. from our handler).
        if kwargs:
            published.append(kwargs)

    with patch(
        "peripheral_controller.services.zstage_state_setter_service.publish_message",
        side_effect=_capture_publish,
    ):
        svc.on_protocol_set_magnet_request(json.dumps({
            "on": True, "height_mm": 12.5,
        }))

    # proxy.zstage.position assigned to 12.5
    assert svc.proxy.zstage.position == 12.5
    assert published == [{"topic": MAGNET_APPLIED, "message": "1"}]


def test_protocol_set_magnet_on_with_sentinel_uses_live_pref():
    """{'on': true, 'height_mm': 0.0} (sentinel = below MIN) -> read
    PeripheralPreferences().up_height_mm and assign that to position."""
    svc = _make_service()
    fake_prefs = MagicMock()
    fake_prefs.up_height_mm = 22.5
    with patch(
        "peripheral_controller.services.zstage_state_setter_service.publish_message",
    ), patch(
        "peripheral_controller.services.zstage_state_setter_service.PeripheralPreferences",
        return_value=fake_prefs,
    ):
        # sentinel = anything < MIN_ZSTAGE_HEIGHT_MM
        svc.on_protocol_set_magnet_request(json.dumps({
            "on": True, "height_mm": MIN_ZSTAGE_HEIGHT_MM - 0.5,
        }))

    # Should have used the live pref value, NOT the sentinel
    assert svc.proxy.zstage.position == 22.5


def test_protocol_set_magnet_does_not_persist_to_prefs():
    """Sentinel: pre-set prefs.up_height_mm = 999; run handler with an
    explicit non-sentinel height; assert pref is unchanged (handler
    reads prefs only when sentinel; never writes prefs)."""
    svc = _make_service()
    fake_prefs = MagicMock()
    fake_prefs.up_height_mm = 999
    with patch(
        "peripheral_controller.services.zstage_state_setter_service.publish_message",
    ), patch(
        "peripheral_controller.services.zstage_state_setter_service.PeripheralPreferences",
        return_value=fake_prefs,
    ):
        svc.on_protocol_set_magnet_request(json.dumps({
            "on": True, "height_mm": 5.0,
        }))

    # Pref should be untouched — sentinel not triggered, pref not read or written
    assert fake_prefs.up_height_mm == 999
