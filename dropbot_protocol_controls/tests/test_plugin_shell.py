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
