# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Portable Dropbot status pane follows the selected protocol step's
voltage and frequency (PROTOCOL_TREE_ROW_SELECTED), except for groups,
empty selections, while a protocol runs, and echoes of its own follow."""

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Bool, List, observe

# Microdrop package imports.
from dropbot_protocol_controls.consts import FREQUENCY_COLUMN_ID, VOLTAGE_COLUMN_ID
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeRowSelectedMessage
from portable_dropbot_controller.consts import FREQUENCY_BOUNDS, VOLTAGE_BOUNDS
from portable_dropbot_status_and_controls.message_handlers.message_handler import (
    PortableDropbotStatusAndControlsMessageHandler,
)
from portable_dropbot_status_and_controls.models.model import (
    PortableDropbotStatusAndControlsModel,
)

LOW_VOLTAGE, HIGH_VOLTAGE = VOLTAGE_BOUNDS
LOW_FREQUENCY, HIGH_FREQUENCY = FREQUENCY_BOUNDS


class FollowRecordingModel(PortableDropbotStatusAndControlsModel):
    """The pane model, recording ``following_step`` at every voltage write."""

    #: ``following_step`` as seen by each voltage change, in order.
    following_during_voltage_writes = List(Bool)

    @observe("voltage", post_init=True)
    def _record_following_step(self, event):
        self.following_during_voltage_writes.append(self.following_step)


@pytest.fixture
def handler(request):
    """A handler on a real model, both setpoints parked at their range's top
    so a step at the bottom is always a change."""
    model = FollowRecordingModel(voltage=HIGH_VOLTAGE, frequency=HIGH_FREQUENCY)
    message_handler = PortableDropbotStatusAndControlsMessageHandler(
        model=model, name=f"test_{request.node.name}"
    )

    yield message_handler

    message_handler.teardown()


def _row_selected(step_id="step-1", **cells):
    return ProtocolTreeRowSelectedMessage(step_id=step_id, cells=cells).serialize()


def test_step_selection_sets_voltage_and_frequency(handler):
    handler._on_row_selected_triggered(
        _row_selected(
            **{VOLTAGE_COLUMN_ID: LOW_VOLTAGE, FREQUENCY_COLUMN_ID: LOW_FREQUENCY}
        )
    )

    assert handler.model.voltage == LOW_VOLTAGE
    assert handler.model.frequency == LOW_FREQUENCY


def test_group_or_empty_selection_leaves_setpoints(handler):
    cells = {VOLTAGE_COLUMN_ID: LOW_VOLTAGE, FREQUENCY_COLUMN_ID: LOW_FREQUENCY}

    handler._on_row_selected_triggered(_row_selected(step_id=None, **cells))

    assert (handler.model.voltage, handler.model.frequency) == (
        HIGH_VOLTAGE,
        HIGH_FREQUENCY,
    )


def test_running_protocol_leaves_setpoints(handler):
    handler.model.protocol_running = True
    cells = {VOLTAGE_COLUMN_ID: LOW_VOLTAGE, FREQUENCY_COLUMN_ID: LOW_FREQUENCY}

    handler._on_row_selected_triggered(_row_selected(**cells))

    assert (handler.model.voltage, handler.model.frequency) == (
        HIGH_VOLTAGE,
        HIGH_FREQUENCY,
    )


def test_missing_cell_leaves_that_setpoint(handler):
    handler._on_row_selected_triggered(
        _row_selected(**{VOLTAGE_COLUMN_ID: LOW_VOLTAGE})
    )

    assert handler.model.voltage == LOW_VOLTAGE
    assert handler.model.frequency == HIGH_FREQUENCY


def test_out_of_range_value_is_skipped(handler):
    cells = {VOLTAGE_COLUMN_ID: HIGH_VOLTAGE + 1, FREQUENCY_COLUMN_ID: LOW_FREQUENCY}

    handler._on_row_selected_triggered(_row_selected(**cells))

    assert handler.model.voltage == HIGH_VOLTAGE
    assert handler.model.frequency == LOW_FREQUENCY


def test_pane_override_survives_echo_of_the_same_step(handler):
    step_a = _row_selected("A", **{VOLTAGE_COLUMN_ID: LOW_VOLTAGE})

    handler._on_row_selected_triggered(step_a)
    assert handler.model.voltage == LOW_VOLTAGE

    handler.model.voltage = LOW_VOLTAGE + 1  # the user overrides it in the pane
    handler._on_row_selected_triggered(step_a)
    assert handler.model.voltage == LOW_VOLTAGE + 1

    handler._on_row_selected_triggered(
        _row_selected("A", **{VOLTAGE_COLUMN_ID: LOW_VOLTAGE + 2})
    )
    assert handler.model.voltage == LOW_VOLTAGE + 2

    handler._on_row_selected_triggered(
        _row_selected("B", **{VOLTAGE_COLUMN_ID: LOW_VOLTAGE})
    )
    assert handler.model.voltage == LOW_VOLTAGE


def test_reselecting_a_step_after_a_group_follows_again(handler):
    step_a = _row_selected("A", **{VOLTAGE_COLUMN_ID: LOW_VOLTAGE})

    handler._on_row_selected_triggered(step_a)
    handler.model.voltage = LOW_VOLTAGE + 1
    handler._on_row_selected_triggered(_row_selected(step_id=None))
    handler._on_row_selected_triggered(step_a)

    assert handler.model.voltage == LOW_VOLTAGE


def test_reselecting_a_step_after_a_step_without_the_cell_follows_again(handler):
    step_a = _row_selected("A", **{VOLTAGE_COLUMN_ID: LOW_VOLTAGE})

    handler._on_row_selected_triggered(step_a)
    handler.model.voltage = LOW_VOLTAGE + 1
    handler._on_row_selected_triggered(_row_selected("B"))
    assert handler.model.voltage == LOW_VOLTAGE + 1

    handler._on_row_selected_triggered(step_a)
    assert handler.model.voltage == LOW_VOLTAGE


def test_following_step_is_raised_only_while_a_follow_writes(handler):
    handler._on_row_selected_triggered(
        _row_selected(**{VOLTAGE_COLUMN_ID: LOW_VOLTAGE})
    )
    handler.model.voltage = LOW_VOLTAGE + 1  # a user edit

    assert handler.model.following_during_voltage_writes == [True, False]
    assert not handler.model.following_step
