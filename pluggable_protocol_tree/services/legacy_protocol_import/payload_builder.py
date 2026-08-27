# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Reconcile converted legacy values against the live column set.

The converter deliberately knows nothing about which plugins are loaded,
so this is where its plain dicts meet the dynamic row type. A value whose
target column is absent -- a heater setpoint with the heater plugin
unloaded, say -- is recorded as dropped rather than raising.
"""

from pluggable_protocol_tree.consts import ELECTRODE_TO_CHANNEL_KEY
from pluggable_protocol_tree.models.row_manager import RowManager

from logger.logger_service import get_logger

from .consts import (
    IMPORTED_PROTOCOL_GROUP_NAME, REPEAT_DURATION_CONTROLS_FLAG,
    REPETITIONS_COLUMN_ID,
)

logger = get_logger(__name__)


def _settable_attribute_names(manager) -> set:
    """Attribute names the current dynamic step type actually carries.

    A legacy value whose name is missing here has no column in this build --
    e.g. a heater setpoint with the heater plugin unloaded."""
    return set(manager.step_type().trait_names())


def _repeats_group_path(manager, converted):
    """Path the steps should be added under.

    ``n_repeats`` cannot live on the root: the root carries no
    ``repetitions`` attribute and ``serialize_tree`` skips it, so the value
    would vanish. A repeated protocol therefore gets one wrapper group that
    does serialize; an unrepeated one stays flat, matching the legacy shape.

    When this build's column set has no repetitions column at all, the
    group type carries no ``repetitions`` attribute either -- a wrapper
    group would then be a pointless one-child group with nowhere to put
    the repeat count. Skip creating it and just record the drop."""
    if converted.protocol_repeats <= 1:
        return ()
    if REPETITIONS_COLUMN_ID not in manager.group_type.class_trait_names():
        converted.report.record_dropped(REPETITIONS_COLUMN_ID)
        return ()
    group_path = manager.add_group(name=IMPORTED_PROTOCOL_GROUP_NAME)
    group_row = manager.get_row(group_path)
    setattr(group_row, REPETITIONS_COLUMN_ID, converted.protocol_repeats)
    return group_path


def build_protocol_payload(converted, columns: list) -> dict:
    """Build a payload in ``RowManager.to_json()`` shape from ``converted``.

    Records every value with no matching column on ``converted.report``, so
    the summary dialog can tell the user what their build could not hold."""
    manager = RowManager(columns=list(columns))
    settable = _settable_attribute_names(manager)
    parent_path = _repeats_group_path(manager, converted)

    for values in converted.step_values:
        values = dict(values)
        repeat_duration_controls = values.pop(
            REPEAT_DURATION_CONTROLS_FLAG, None)
        applicable = {}
        for column_id, value in values.items():
            if column_id in settable:
                applicable[column_id] = value
            else:
                converted.report.record_dropped(column_id)
        path = manager.add_step(parent_path=parent_path, values=applicable)
        if repeat_duration_controls:
            manager.get_row(path).repeat_duration_controls = True

    manager.protocol_metadata[ELECTRODE_TO_CHANNEL_KEY] = dict(
        converted.electrode_to_channel)
    return manager.to_json()
