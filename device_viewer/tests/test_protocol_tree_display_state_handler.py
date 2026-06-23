"""Tests for the DV-side handler that adapts ProtocolTreeDisplayMessage
to the existing DeviceViewerMessageModel pipeline."""

from unittest.mock import MagicMock

from device_viewer.consts import (
    PROTOCOL_TREE_DISPLAY_STATE, ACTOR_TOPIC_DICT, listener_name,
)
from device_viewer.models.messages import DeviceViewerMessageModel
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)


def test_topic_in_actor_topic_dict():
    assert PROTOCOL_TREE_DISPLAY_STATE in ACTOR_TOPIC_DICT[listener_name]


def test_handler_emits_adapted_message_via_display_state_signal():
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewerDockPane,
    )
    pane = MagicMock()
    # The handler reads the real electrodes Property `electrode_ids_channels_map`
    # and asks the routes model for a layer color via get_available_color().
    pane.model.electrodes.electrode_ids_channels_map = {
        "e00": 0, "e01": 1, "e02": 2, "missing": None,
    }
    pane.model.routes.get_available_color.return_value = "blue"
    msg = ProtocolTreeDisplayMessage(
        electrodes=["e00", "e01", "missing"],
        routes=[["e02", "e00"]],
        step_id="uuid-abc", step_label="Wash",
        free_mode=False, editable=True,
    )
    DeviceViewerDockPane._on_protocol_tree_display_state_triggered(
        pane, msg.serialize(),
    )

    pane.device_view.display_state_signal.emit.assert_called_once()
    serial = pane.device_view.display_state_signal.emit.call_args.args[0]
    rich = DeviceViewerMessageModel.deserialize(serial)
    assert rich.channels_activated == {0, 1}        # "missing" dropped
    assert rich.routes == [(["e02", "e00"], "blue")]
    assert rich.step_info == {
        "step_id": "uuid-abc", "step_label": "Wash", "free_mode": False,
    }
    assert rich.editable is True


def test_free_mode_payload_clears_display():
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewerDockPane,
    )
    pane = MagicMock()
    pane.model.electrodes.electrode_ids_channels_map = {"e00": 0, "e01": 1}
    msg = ProtocolTreeDisplayMessage(free_mode=True)
    DeviceViewerDockPane._on_protocol_tree_display_state_triggered(
        pane, msg.serialize(),
    )
    serial = pane.device_view.display_state_signal.emit.call_args.args[0]
    rich = DeviceViewerMessageModel.deserialize(serial)
    assert rich.channels_activated == set()
    assert rich.routes == []
    assert rich.step_info == {
        "step_id": None, "step_label": None, "free_mode": True,
    }
