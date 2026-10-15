# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The DropBot status pane follows the selected protocol step's voltage and
frequency (PROTOCOL_TREE_ROW_SELECTED), except for groups, empty
selections, while a protocol runs, and echoes of its own follow."""

# Third-party imports.
import pytest

# Microdrop package imports.
from dropbot_preferences_ui.consts import (
    UI_DEFAULT_FREQUENCY_KEY,
    UI_DEFAULT_VOLTAGE_KEY,
)
from dropbot_protocol_controls.consts import FREQUENCY_COLUMN_ID, VOLTAGE_COLUMN_ID
from dropbot_status_and_controls.message_handler import (
    DropbotStatusAndControlsMessageHandler,
)
from dropbot_status_and_controls.model import DropbotStatusAndControlsModel
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeRowSelectedMessage


@pytest.fixture
def handler(request):
    """A handler on a real model, both setpoints parked at their range's top
    so a step at the bottom is always a change. Setting them persists the
    saved UI defaults to app_globals, so the live values are put back."""
    app_globals = get_microdrop_redis_globals_manager()
    saved_defaults = {
        key: app_globals[key]
        for key in (UI_DEFAULT_VOLTAGE_KEY, UI_DEFAULT_FREQUENCY_KEY)
        if key in app_globals
    }

    model = DropbotStatusAndControlsModel()
    model.voltage = _bounds(model, "voltage")[1]
    model.frequency = _bounds(model, "frequency")[1]

    message_handler = DropbotStatusAndControlsMessageHandler(
        model=model, name=f"test_{request.node.name}"
    )

    yield message_handler

    message_handler.teardown()

    for key, value in saved_defaults.items():
        app_globals[key] = value


def _bounds(model, trait_name):
    """The (low, high) of one of the model's Range setpoints."""
    trait_handler = model.trait(trait_name).handler

    return trait_handler._low, trait_handler._high


def _row_selected(step_id="step-1", **cells):
    return ProtocolTreeRowSelectedMessage(step_id=step_id, cells=cells).serialize()


def test_step_selection_sets_voltage_and_frequency(handler):
    voltage = _bounds(handler.model, "voltage")[0]
    frequency = _bounds(handler.model, "frequency")[0]

    handler._on_row_selected_triggered(
        _row_selected(**{VOLTAGE_COLUMN_ID: voltage, FREQUENCY_COLUMN_ID: frequency})
    )

    assert handler.model.voltage == voltage
    assert handler.model.frequency == frequency


def test_group_or_empty_selection_leaves_setpoints(handler):
    before = (handler.model.voltage, handler.model.frequency)
    cells = {
        VOLTAGE_COLUMN_ID: _bounds(handler.model, "voltage")[0],
        FREQUENCY_COLUMN_ID: _bounds(handler.model, "frequency")[0],
    }

    handler._on_row_selected_triggered(_row_selected(step_id=None, **cells))

    assert (handler.model.voltage, handler.model.frequency) == before


def test_running_protocol_leaves_setpoints(handler):
    handler.model.protocol_running = True
    before = (handler.model.voltage, handler.model.frequency)
    cells = {
        VOLTAGE_COLUMN_ID: _bounds(handler.model, "voltage")[0],
        FREQUENCY_COLUMN_ID: _bounds(handler.model, "frequency")[0],
    }

    handler._on_row_selected_triggered(_row_selected(**cells))

    assert (handler.model.voltage, handler.model.frequency) == before


def test_missing_cell_leaves_that_setpoint(handler):
    frequency_before = handler.model.frequency
    voltage = _bounds(handler.model, "voltage")[0]

    handler._on_row_selected_triggered(_row_selected(**{VOLTAGE_COLUMN_ID: voltage}))

    assert handler.model.voltage == voltage
    assert handler.model.frequency == frequency_before


def test_out_of_range_value_is_skipped(handler):
    voltage_before = handler.model.voltage
    frequency = _bounds(handler.model, "frequency")[0]
    cells = {
        VOLTAGE_COLUMN_ID: _bounds(handler.model, "voltage")[1] + 1,
        FREQUENCY_COLUMN_ID: frequency,
    }

    handler._on_row_selected_triggered(_row_selected(**cells))

    assert handler.model.voltage == voltage_before
    assert handler.model.frequency == frequency


def test_pane_override_survives_echo_of_the_same_step(handler):
    low = _bounds(handler.model, "voltage")[0]
    step_a = _row_selected("A", **{VOLTAGE_COLUMN_ID: low})

    handler._on_row_selected_triggered(step_a)
    assert handler.model.voltage == low

    handler.model.voltage = low + 1  # the user overrides it in the pane
    handler._on_row_selected_triggered(step_a)
    assert handler.model.voltage == low + 1

    handler._on_row_selected_triggered(
        _row_selected("A", **{VOLTAGE_COLUMN_ID: low + 2})
    )
    assert handler.model.voltage == low + 2

    handler._on_row_selected_triggered(_row_selected("B", **{VOLTAGE_COLUMN_ID: low}))
    assert handler.model.voltage == low


def test_reselecting_a_step_after_a_group_follows_again(handler):
    low = _bounds(handler.model, "voltage")[0]
    step_a = _row_selected("A", **{VOLTAGE_COLUMN_ID: low})

    handler._on_row_selected_triggered(step_a)
    handler.model.voltage = low + 1
    handler._on_row_selected_triggered(_row_selected(step_id=None))
    handler._on_row_selected_triggered(step_a)

    assert handler.model.voltage == low


def test_reselecting_a_step_after_a_step_without_the_cell_follows_again(handler):
    low = _bounds(handler.model, "voltage")[0]
    step_a = _row_selected("A", **{VOLTAGE_COLUMN_ID: low})

    handler._on_row_selected_triggered(step_a)
    handler.model.voltage = low + 1
    handler._on_row_selected_triggered(_row_selected("B"))
    assert handler.model.voltage == low + 1

    handler._on_row_selected_triggered(step_a)
    assert handler.model.voltage == low
