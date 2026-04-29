"""Smoke tests for the dropbot_protocol_controls package shell."""

def test_can_import_plugin():
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
    p = DropbotProtocolControlsPlugin()
    assert p.id.endswith(".plugin")


def test_plugin_instantiates_with_no_columns_yet():
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
    p = DropbotProtocolControlsPlugin()
    # contributed_protocol_columns may be empty until task 11 wires it up.
    assert hasattr(p, "id")
    assert hasattr(p, "name")


from unittest.mock import patch


def test_plugin_contributes_voltage_and_frequency_columns():
    """The plugin's contributed_protocol_columns default factory yields
    a list containing both voltage and frequency Column instances."""
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin

    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000

        p = DropbotProtocolControlsPlugin()
        col_ids = [c.model.col_id for c in p.contributed_protocol_columns]

    assert "voltage" in col_ids
    assert "frequency" in col_ids


def test_actor_topic_routing_contributes_calibration_listener():
    """The plugin contributes ACTOR_TOPIC_DICT routing the
    calibration_data_listener actor to the CALIBRATION_DATA topic, so
    MessageRouterPlugin.start() wires the subscription automatically."""
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
    from dropbot_protocol_controls.consts import (
        ACTOR_TOPIC_DICT, CALIBRATION_LISTENER_ACTOR_NAME,
    )
    from device_viewer.consts import CALIBRATION_DATA

    p = DropbotProtocolControlsPlugin()
    assert p.actor_topic_routing == [ACTOR_TOPIC_DICT]
    assert ACTOR_TOPIC_DICT[CALIBRATION_LISTENER_ACTOR_NAME] == [CALIBRATION_DATA]
    assert CALIBRATION_LISTENER_ACTOR_NAME == "calibration_data_listener"
