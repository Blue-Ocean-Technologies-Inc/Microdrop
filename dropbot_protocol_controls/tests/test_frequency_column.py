"""Tests for the frequency column — model, factory, view, handler."""

from unittest.mock import MagicMock, patch

from traits.api import HasTraits

from dropbot_protocol_controls.protocol_columns.frequency_column import (
    FrequencyColumnModel, make_frequency_column,
)


def test_frequency_column_model_id_and_name():
    m = FrequencyColumnModel(col_id="frequency", col_name="Frequency (Hz)",
                             default_value=10000)
    assert m.col_id == "frequency"
    assert m.col_name == "Frequency (Hz)"
    assert m.default_value == 10000


def test_frequency_column_trait_for_row_is_int():
    m = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                             default_value=10000)
    trait = m.trait_for_row()
    class Row(HasTraits):
        frequency = trait
    r = Row()
    assert r.frequency == 10000
    r.frequency = 5000
    assert r.frequency == 5000
    assert isinstance(r.frequency, int)


def test_frequency_column_serialize_identity():
    m = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                             default_value=10000)
    assert m.serialize(10000) == 10000
    assert m.deserialize(10000) == 10000


def test_make_frequency_column_returns_column_with_frequency_id():
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_frequency = 10000
        col = make_frequency_column()
    assert col.model.col_id == "frequency"


def test_make_frequency_column_default_reads_from_prefs():
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_frequency = 5000
        col = make_frequency_column()
    assert col.model.default_value == 5000


from dropbot_controller.consts import PROTOCOL_SET_FREQUENCY, FREQUENCY_APPLIED


def test_frequency_handler_priority_20():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    assert handler.priority == 20


def test_frequency_handler_wait_for_topics_includes_frequency_applied():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    assert FREQUENCY_APPLIED in handler.wait_for_topics


def test_frequency_handler_on_step_publishes_and_waits():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    row = MagicMock()
    row.frequency = 8000
    ctx = MagicMock()

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published == [{"topic": PROTOCOL_SET_FREQUENCY, "message": "8000"}]
    ctx.wait_for.assert_called_once_with(FREQUENCY_APPLIED, timeout=5.0)


def test_frequency_handler_on_step_publishes_int_payload():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    row = MagicMock()
    row.frequency = 5000.9  # float — should be coerced
    ctx = MagicMock()

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published[0]["message"] == "5000"


def test_frequency_handler_on_interact_writes_through_to_row():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler, FrequencyColumnModel,
    )
    handler = FrequencyHandler()
    model = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                                  default_value=10000)
    handler.model = model

    class FakeRow:
        frequency = 10000
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ):
        handler.on_interact(row, model, 5000)

    assert row.frequency == 5000


def test_frequency_handler_on_interact_persists_to_prefs():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler, FrequencyColumnModel,
    )
    handler = FrequencyHandler()
    model = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                                  default_value=10000)
    handler.model = model

    class FakeRow:
        frequency = 10000
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        prefs_instance = MockPrefs.return_value
        handler.on_interact(row, model, 5000)

    MockPrefs.assert_called_once_with()
    assert prefs_instance.last_frequency == 5000
