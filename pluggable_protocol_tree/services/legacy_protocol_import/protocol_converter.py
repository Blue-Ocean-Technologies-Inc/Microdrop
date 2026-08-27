# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Map a legacy protocol onto new-format column values.

Emits plain per-step dicts keyed by new column id rather than a finished
JSON payload, so this module stays independent of which plugins happen to
be loaded. Reconciling those dicts against the live column set -- and
reporting values whose target column is absent -- happens in
``payload_builder``.
"""

from traits.api import Dict, HasTraits, Instance, Int, List

from logger.logger_service import get_logger

from .consts import (
    DMF_DEVICE_UI_PLUGIN, DROPBOT_PLUGIN, DROPLET_PLANNING_PLUGIN,
    DROPPED_LEGACY_FIELDS, DURATION_COLUMN_ID, ELECTRODE_CONTROLLER_PLUGIN,
    ELECTRODES_COLUMN_ID, FREQUENCY_COLUMN_ID, LEGACY_DROP_ROUTES_FIELD,
    LEGACY_DURATION_FIELD, LEGACY_ELECTRODE_STATES_FIELD,
    LEGACY_FREQUENCY_FIELD, LEGACY_HEATER_FIELD,
    LEGACY_HEATER_TEMPERATURE_FIELD, LEGACY_LABEL_FIELD, LEGACY_MAGNET_FIELD,
    LEGACY_MESSAGE_FIELD, LEGACY_REPEAT_DURATION_FIELD,
    LEGACY_ROUTE_ELECTRODE_COLUMN, LEGACY_ROUTE_INDEX_COLUMN,
    LEGACY_ROUTE_REPEATS_FIELD, LEGACY_ROUTE_TRANSITION_COLUMN,
    LEGACY_TRAIL_LENGTH_FIELD, LEGACY_VIDEO_ENABLED_FIELD,
    LEGACY_VOLTAGE_FIELD, LEGACY_VOLUME_THRESHOLD_FIELD, MAGNET_ON_FIELD_ID,
    MESSAGE_PROMPT_COLUMN_ID, MR_BOX_PLUGIN, NAME_COLUMN_ID,
    REPEAT_DURATION_COLUMN_ID, REPEAT_DURATION_CONTROLS_FLAG,
    ROUTE_REPETITIONS_COLUMN_ID, ROUTES_COLUMN_ID, SET_MAGNET_FIELD_ID,
    SET_TEMPERATURE_FIELD_ID, STEP_LABEL_PLUGIN,
    TARGET_TEMPERATURE_FIELD_ID, TRAIL_LENGTH_COLUMN_ID, USER_PROMPT_PLUGIN,
    VIDEO_COLUMN_ID, VOLTAGE_COLUMN_ID, VOLUME_THRESHOLD_COLUMN_ID,
    VOLUME_THRESHOLD_MAX_PERCENT, VOLUME_THRESHOLD_MIN_PERCENT,
    VOLUME_THRESHOLD_PERCENT_SCALE, ZIKA_BOX_PLUGIN,
)
from .conversion_report import ConversionReport

logger = get_logger(__name__)


class ConvertedProtocol(HasTraits):
    """Result of converting one legacy protocol, before it meets any columns."""

    step_values = List(Dict())
    protocol_repeats = Int(1)
    electrode_to_channel = Dict()
    report = Instance(ConversionReport)


def _active_electrode_ids(states, electrode_to_channel, report) -> list:
    """Electrode ids the step switches on, minus any the device no longer
    has. Real protocols do reference electrodes deleted from their SVG."""
    active = []
    for electrode_id in states.index:
        if not bool(states[electrode_id]):
            continue
        if electrode_id not in electrode_to_channel:
            report.record_unresolved_electrode(str(electrode_id))
            continue
        active.append(str(electrode_id))
    return active


def _routes_from_drop_routes(frame, electrode_to_channel, report) -> list:
    """Ordered electrode-id lists, one per ``route_i``, ordered within a
    route by ``transition_i``."""
    if frame is None or len(frame) == 0:
        return []
    routes = []
    for _, group in frame.groupby(LEGACY_ROUTE_INDEX_COLUMN, sort=True):
        ordered = group.sort_values(LEGACY_ROUTE_TRANSITION_COLUMN)
        electrode_ids = []
        for electrode_id in ordered[LEGACY_ROUTE_ELECTRODE_COLUMN]:
            if electrode_id not in electrode_to_channel:
                report.record_unresolved_electrode(str(electrode_id))
                continue
            electrode_ids.append(str(electrode_id))
        if electrode_ids:
            routes.append(electrode_ids)
    return routes


def _record_dropped_fields(plugin_data, report) -> None:
    for plugin_name, fields in DROPPED_LEGACY_FIELDS.items():
        present = plugin_data.get(plugin_name)
        if not present:
            continue
        for field in fields:
            if field in present:
                report.record_dropped(f"{plugin_name}.{field}")


def _to_percent(fraction: float) -> int:
    percent = round(float(fraction) * VOLUME_THRESHOLD_PERCENT_SCALE)
    return max(VOLUME_THRESHOLD_MIN_PERCENT,
               min(VOLUME_THRESHOLD_MAX_PERCENT, percent))


def _convert_step(step, index, electrode_to_channel, report) -> dict:
    plugin_data = step.plugin_data
    values = {}

    electrode_controller = plugin_data.get(ELECTRODE_CONTROLLER_PLUGIN, {})
    if LEGACY_VOLTAGE_FIELD in electrode_controller:
        values[VOLTAGE_COLUMN_ID] = round(
            float(electrode_controller[LEGACY_VOLTAGE_FIELD]))
    if LEGACY_FREQUENCY_FIELD in electrode_controller:
        values[FREQUENCY_COLUMN_ID] = round(
            float(electrode_controller[LEGACY_FREQUENCY_FIELD]))
    if LEGACY_DURATION_FIELD in electrode_controller:
        values[DURATION_COLUMN_ID] = float(
            electrode_controller[LEGACY_DURATION_FIELD])
    if LEGACY_ELECTRODE_STATES_FIELD in electrode_controller:
        values[ELECTRODES_COLUMN_ID] = _active_electrode_ids(
            electrode_controller[LEGACY_ELECTRODE_STATES_FIELD],
            electrode_to_channel, report)

    droplet_planning = plugin_data.get(DROPLET_PLANNING_PLUGIN, {})
    if LEGACY_DROP_ROUTES_FIELD in droplet_planning:
        values[ROUTES_COLUMN_ID] = _routes_from_drop_routes(
            droplet_planning[LEGACY_DROP_ROUTES_FIELD],
            electrode_to_channel, report)
    if LEGACY_ROUTE_REPEATS_FIELD in droplet_planning:
        values[ROUTE_REPETITIONS_COLUMN_ID] = int(
            droplet_planning[LEGACY_ROUTE_REPEATS_FIELD])
    if LEGACY_REPEAT_DURATION_FIELD in droplet_planning:
        repeat_duration = float(
            droplet_planning[LEGACY_REPEAT_DURATION_FIELD])
        values[REPEAT_DURATION_COLUMN_ID] = repeat_duration
        values[REPEAT_DURATION_CONTROLS_FLAG] = repeat_duration > 0
    if LEGACY_TRAIL_LENGTH_FIELD in droplet_planning:
        values[TRAIL_LENGTH_COLUMN_ID] = int(
            droplet_planning[LEGACY_TRAIL_LENGTH_FIELD])

    step_label = plugin_data.get(STEP_LABEL_PLUGIN, {})
    label = str(step_label.get(LEGACY_LABEL_FIELD, "") or "").strip()
    values[NAME_COLUMN_ID] = label or f"Step {index + 1}"

    user_prompt = plugin_data.get(USER_PROMPT_PLUGIN, {})
    if LEGACY_MESSAGE_FIELD in user_prompt:
        values[MESSAGE_PROMPT_COLUMN_ID] = str(
            user_prompt[LEGACY_MESSAGE_FIELD] or "")

    dropbot = plugin_data.get(DROPBOT_PLUGIN, {})
    if LEGACY_VOLUME_THRESHOLD_FIELD in dropbot:
        values[VOLUME_THRESHOLD_COLUMN_ID] = _to_percent(
            dropbot[LEGACY_VOLUME_THRESHOLD_FIELD])

    device_ui = plugin_data.get(DMF_DEVICE_UI_PLUGIN, {})
    if LEGACY_VIDEO_ENABLED_FIELD in device_ui:
        values[VIDEO_COLUMN_ID] = bool(
            device_ui[LEGACY_VIDEO_ENABLED_FIELD])

    # Magnet may come from either peripheral box. zika_box is the later,
    # more specific one, so it wins and the shadowed value is reported.
    mr_box = plugin_data.get(MR_BOX_PLUGIN, {})
    zika_box = plugin_data.get(ZIKA_BOX_PLUGIN, {})
    if LEGACY_MAGNET_FIELD in zika_box:
        values[SET_MAGNET_FIELD_ID] = True
        values[MAGNET_ON_FIELD_ID] = bool(zika_box[LEGACY_MAGNET_FIELD])
        if LEGACY_MAGNET_FIELD in mr_box:
            report.record_dropped(f"{MR_BOX_PLUGIN}.{LEGACY_MAGNET_FIELD}")
    elif LEGACY_MAGNET_FIELD in mr_box:
        values[SET_MAGNET_FIELD_ID] = True
        values[MAGNET_ON_FIELD_ID] = bool(mr_box[LEGACY_MAGNET_FIELD])

    if LEGACY_HEATER_FIELD in zika_box:
        values[SET_TEMPERATURE_FIELD_ID] = bool(zika_box[LEGACY_HEATER_FIELD])
        if LEGACY_HEATER_TEMPERATURE_FIELD in zika_box:
            values[TARGET_TEMPERATURE_FIELD_ID] = float(
                zika_box[LEGACY_HEATER_TEMPERATURE_FIELD])

    _record_dropped_fields(plugin_data, report)
    return values


def convert_legacy_protocol(protocol, electrode_to_channel: dict):
    """Convert every step of ``protocol`` into new-format column values.

    A step that fails to convert is emitted empty (so it keeps its position
    in the sequence) and recorded in the report -- one bad step must not
    abort a 177-step protocol."""
    report = ConversionReport(step_count=len(protocol.steps))
    step_values = []
    for index, step in enumerate(protocol.steps):
        try:
            values = _convert_step(step, index, electrode_to_channel, report)
        except Exception as e:
            logger.warning(
                f"step {index + 1} of {protocol.name!r} failed to convert: "
                f"{e}", exc_info=True)
            report.record_step_failure(f"Step {index + 1}: {e}")
            values = {NAME_COLUMN_ID: f"Step {index + 1}"}
        for column_id in values:
            # A row flag (consumed by payload_builder to set
            # repeat_duration_controls on the row), not a column -- would
            # otherwise show up as a bogus entry on the report's "Mapped:"
            # line.
            if column_id == REPEAT_DURATION_CONTROLS_FLAG:
                continue
            report.record_mapped(column_id)
        step_values.append(values)
    return ConvertedProtocol(
        step_values=step_values,
        protocol_repeats=int(protocol.n_repeats or 1),
        electrode_to_channel=dict(electrode_to_channel),
        report=report,
    )
