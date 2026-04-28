"""Smoke tests for the peripheral_protocol_controls package shell."""

def test_can_import_plugin():
    """Envisage Plugin.id is a Trait — accessible on an instance, not the
    class. (Class-level access raises AttributeError.)"""
    from peripheral_protocol_controls.plugin import (
        PeripheralProtocolControlsPlugin,
    )
    p = PeripheralProtocolControlsPlugin()
    assert p.id.endswith(".plugin")


def test_plugin_instantiates_with_no_columns_yet():
    from peripheral_protocol_controls.plugin import (
        PeripheralProtocolControlsPlugin,
    )
    p = PeripheralProtocolControlsPlugin()
    assert hasattr(p, "id")
    assert hasattr(p, "name")
