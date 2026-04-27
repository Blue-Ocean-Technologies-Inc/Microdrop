"""JSON persistence round-trip for Int voltage/frequency columns."""

import json
from unittest.mock import patch

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column

from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)


def _build_columns():
    """Patch DropbotPreferences so column factories don't need an envisage app."""
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_voltage_column(), make_frequency_column(),
        ]


def test_voltage_frequency_int_round_trip_through_json():
    cols = _build_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "voltage": 120, "frequency": 5000})

    payload = rm.to_json()
    json_str = json.dumps(payload)  # Confirms it's JSON-serializable
    parsed = json.loads(json_str)

    rm2 = RowManager.from_json(parsed, columns=_build_columns())
    step = rm2.root.children[0]
    assert step.voltage == 120
    assert step.frequency == 5000
    assert isinstance(step.voltage, int)
    assert isinstance(step.frequency, int)
