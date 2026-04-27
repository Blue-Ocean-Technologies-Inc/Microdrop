"""Tests for the voltage column — model, factory, view, handler."""

from unittest.mock import MagicMock, patch

from traits.api import HasTraits

from dropbot_protocol_controls.protocol_columns.voltage_column import (
    VoltageColumnModel, make_voltage_column,
)


def test_voltage_column_model_id_and_name():
    m = VoltageColumnModel(col_id="voltage", col_name="Voltage (V)",
                           default_value=100)
    assert m.col_id == "voltage"
    assert m.col_name == "Voltage (V)"
    assert m.default_value == 100


def test_voltage_column_trait_for_row_is_int():
    """Row trait stores Int — never Float."""
    m = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    trait = m.trait_for_row()
    class Row(HasTraits):
        voltage = trait
    r = Row()
    assert r.voltage == 100
    r.voltage = 75
    assert r.voltage == 75
    assert isinstance(r.voltage, int)


def test_voltage_column_serialize_identity():
    m = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    assert m.serialize(100) == 100
    assert m.deserialize(100) == 100


def test_make_voltage_column_returns_column_with_voltage_id():
    """Factory yields a Column whose model.col_id is 'voltage'."""
    # Patch DropbotPreferences so test doesn't need a real envisage app.
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_voltage = 100
        col = make_voltage_column()
    assert col.model.col_id == "voltage"
    assert col.view is not None
    assert col.handler is not None


def test_make_voltage_column_default_reads_from_prefs():
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_voltage = 75
        col = make_voltage_column()
    assert col.model.default_value == 75


from dropbot_controller.consts import PROTOCOL_SET_VOLTAGE, VOLTAGE_APPLIED


def test_voltage_handler_priority_20():
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    assert handler.priority == 20


def test_voltage_handler_wait_for_topics_includes_voltage_applied():
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    assert VOLTAGE_APPLIED in handler.wait_for_topics


def test_voltage_handler_on_step_publishes_and_waits():
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    row = MagicMock()
    row.voltage = 120
    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published == [{"topic": PROTOCOL_SET_VOLTAGE, "message": "120"}]
    ctx.wait_for.assert_called_once_with(VOLTAGE_APPLIED, timeout=5.0)


def test_voltage_handler_on_step_publishes_int_payload():
    """Even if row.voltage is somehow a float, payload is a stringified int."""
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    row = MagicMock()
    row.voltage = 99.7  # float — should be coerced to int
    ctx = MagicMock()

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published[0]["message"] == "99"  # int(99.7) = 99


def test_voltage_handler_on_interact_writes_through_to_row():
    """super().on_interact behavior: model.set_value writes to row."""
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler, VoltageColumnModel,
    )
    handler = VoltageHandler()
    model = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    handler.model = model

    class FakeRow:
        voltage = 100
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ):
        handler.on_interact(row, model, 120)

    assert row.voltage == 120


def test_voltage_handler_on_interact_persists_to_prefs():
    """User cell-edit becomes the new default for next session."""
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler, VoltageColumnModel,
    )
    handler = VoltageHandler()
    model = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    handler.model = model

    class FakeRow:
        voltage = 100
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        prefs_instance = MockPrefs.return_value
        handler.on_interact(row, model, 120)

    MockPrefs.assert_called_once_with()  # no-arg construct hits global prefs
    assert prefs_instance.last_voltage == 120
