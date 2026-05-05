"""Confirm the DropbotProtocolControlsPlugin contributes the new column
and the dialog actor module is imported (which registers the actor)."""

from unittest.mock import patch


def test_make_droplet_check_column_in_plugin_defaults():
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin

    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000

        plugin = DropbotProtocolControlsPlugin()
        cols = plugin._contributed_protocol_columns_default()

    col_ids = [c.model.col_id for c in cols]
    assert "check_droplets" in col_ids


def test_dialog_actor_module_importable():
    # Just importing the module should register the @dramatiq.actor.
    import dropbot_protocol_controls.services.droplet_check_decision_dialog_actor  # noqa: F401


def test_actor_topic_routing_includes_decision_request_topic():
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
    from dropbot_protocol_controls.consts import (
        DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        DROPLET_CHECK_DECISION_REQUEST,
    )

    plugin = DropbotProtocolControlsPlugin()
    # actor_topic_routing is List([ACTOR_TOPIC_DICT], ...)
    routing = plugin.actor_topic_routing[0]
    assert routing[DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME] == [
        DROPLET_CHECK_DECISION_REQUEST,
    ]
