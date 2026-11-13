# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Zone Target compound column (#965): per step, actuate the first region of
a zone type that has (or lacks) a droplet.

Two cells: the zone type (its id; empty = off for the step) and the
criterion (Has Droplet / No Droplet). At step start (on_pre_step) the
handler requests droplet detection on the union of the zone type's region
channels with the existing DETECT_DROPLETS / DROPLETS_DETECTED round trip,
picks the first region in the zone manager's stored order that meets the
criterion (zone_selection.select_zone_region), and hands its electrodes to
RoutesHandler through EXTRA_STATIC_ELECTRODES_KEY, so they are actuated in
every phase of this step alongside the step's own electrodes and routes.
The row is never modified.

A step with no zone type does nothing (no detection request). A missing zone
type, a failed or timed-out detection, or no matching region fails the step
through the executor's error path. Preview mode skips the column: detection
needs hardware.
"""

# Standard library imports.
import json

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QComboBox
from traits.api import Enum, List, Str

# Microdrop package imports.
from device_viewer.consts import ZONES_KEY
from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from pluggable_protocol_tree.builtins.routes_column import (
    EXTRA_STATIC_ELECTRODES_KEY,
)
from pluggable_protocol_tree.consts import (
    ELECTRODE_TO_CHANNEL_KEY,
    protocol_logging_data_contribution_publisher,
)
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
    BaseCompoundColumnModel,
    CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.combobox import ComboBoxColumnView

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    ZONE_CRITERIA,
    ZONE_TARGET_BASE_ID,
    ZONE_TARGET_CRITERION_FIELD_ID,
    ZONE_TARGET_DEFAULT_ACK_TIME_S,
    ZONE_TARGET_FIELD_ID,
    ZONE_TARGET_PRIORITY,
)
from ..zone_selection import (
    select_zone_region,
    zone_detection_channels,
    zone_regions,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()

#: Label of the zone-type choice that turns the column off for a step.
ZONE_TARGET_OFF_LABEL = "(none)"


def read_zones_snapshot():
    """The device viewer's zones snapshot, or {} when none is published.

    Raises whatever the Redis read raises; callers that only decorate the
    UI catch it, the run-time handler lets it fail the step.
    """
    return app_globals.get(ZONES_KEY) or {}


class ZoneTargetCompoundModel(BaseCompoundColumnModel):
    """Zone type id + criterion. base_id 'zone_target' appears as
    compound_id on each field's column entry in the protocol JSON."""

    base_id = ZONE_TARGET_BASE_ID

    def field_specs(self):
        return [
            FieldSpec(ZONE_TARGET_FIELD_ID, "Zone Target", ""),
            FieldSpec(
                ZONE_TARGET_CRITERION_FIELD_ID, "Zone Criterion", ZONE_CRITERIA[0]
            ),
        ]

    def trait_for_field(self, field_id):
        if field_id == ZONE_TARGET_FIELD_ID:
            return Str("", desc="Zone type id whose regions are checked; empty = off")

        if field_id == ZONE_TARGET_CRITERION_FIELD_ID:
            return Enum(
                *ZONE_CRITERIA, desc="Whether the chosen region has or lacks a droplet"
            )

        raise KeyError(field_id)

    def deserialize(self, field_id, raw):
        if field_id == ZONE_TARGET_FIELD_ID:
            return raw or ""

        if field_id == ZONE_TARGET_CRITERION_FIELD_ID and raw not in ZONE_CRITERIA:
            logger.warning(
                f"Unknown zone criterion {raw!r} in protocol; "
                f"using {ZONE_CRITERIA[0]!r}"
            )

            return ZONE_CRITERIA[0]

        return super().deserialize(field_id, raw)


class ZoneTypeComboBoxView(ComboBoxColumnView):
    """Zone type picker. The choices are read from the zones snapshot when
    the editor opens, so they follow the loaded device; a stored zone type
    that no longer exists stays selectable (marked missing) so editing a
    step never silently drops it. The tooltip lists the regions in the
    order they are checked."""

    hidden_by_default = True

    def create_editor(self, parent, context):
        editor = QComboBox(parent)
        editor.addItem(ZONE_TARGET_OFF_LABEL, "")

        for zone_id, zone in self._zones_for_ui().items():
            editor.addItem(zone.get("name") or zone_id, zone_id)

        return editor

    def set_editor_data(self, editor, value):
        index = editor.findData(value or "")

        if index < 0:
            editor.addItem(f"{value} (missing)", value)
            index = editor.count() - 1

        editor.setCurrentIndex(index)

    def get_editor_data(self, editor):
        return editor.currentData() or ""

    def get_tooltip(self, row):
        zone_id = getattr(row, ZONE_TARGET_FIELD_ID, "")

        if not zone_id:
            return (
                "Pick a zone type: at step start, the first of its regions "
                "meeting the Zone Criterion is actuated with the step"
            )

        regions = zone_regions(self._zones_for_ui(), zone_id)

        if regions is None:
            return (
                f"Zone type {zone_id!r} is not defined on the loaded device; "
                "this step fails when run"
            )

        order = ", ".join(region["id"] for region in regions) or "no regions"

        return f"Regions, checked in this order: {order}"

    @staticmethod
    def _zones_for_ui():
        try:
            return read_zones_snapshot()

        except Exception:
            # Decoration only: without Redis the picker still offers "(none)"
            # and keeps the stored value.
            logger.warning("Zones snapshot unavailable", exc_info=True)

            return {}


class ZoneCriterionComboBoxView(ComboBoxColumnView):
    """Read-only and blank while the step has no zone type (same cross-cell
    pattern as the Capture column's capture_at cell)."""

    hidden_by_default = True

    #: get_flags/format_display depend on the zone type cell.
    depends_on_row_traits = List(Str, value=[ZONE_TARGET_FIELD_ID])

    def _options_default(self):
        return list(ZONE_CRITERIA)

    def get_flags(self, row):
        flags = super().get_flags(row)

        if not getattr(row, ZONE_TARGET_FIELD_ID, ""):
            flags &= ~Qt.ItemIsEditable

        return flags

    def format_display(self, value, row):
        if not getattr(row, ZONE_TARGET_FIELD_ID, ""):
            return ""

        return super().format_display(value, row)


class ZoneTargetHandler(BaseCompoundColumnHandler):
    """Resolve the step's zone target in on_pre_step (see module docstring).

    Priority 25: on_pre_step of every bucket runs before any on_step, so
    RoutesHandler (30) sees the added electrodes; 25 also keeps it out of the
    buckets that share the DROPLETS_DETECTED mailbox (volume threshold 30,
    droplet check 80).
    """

    priority = ZONE_TARGET_PRIORITY
    wait_for_topics = [DROPLETS_DETECTED]
    default_ack_time_s = ZONE_TARGET_DEFAULT_ACK_TIME_S

    def on_pre_step(self, row, ctx):
        zone_id = getattr(row, ZONE_TARGET_FIELD_ID, "")

        if not zone_id:
            return

        step = f"Step {row.dotted_path()}"
        criterion = getattr(row, ZONE_TARGET_CRITERION_FIELD_ID, ZONE_CRITERIA[0])

        if getattr(ctx.protocol, "preview_mode", False):
            logger.info(
                f"{step}: preview mode, zone target {zone_id!r} not resolved "
                "(droplet detection needs hardware)"
            )

            return

        regions = zone_regions(read_zones_snapshot(), zone_id)

        if regions is None:
            raise RuntimeError(
                f"{step}: zone type {zone_id!r} is not defined on the loaded "
                "device. Pick another zone type or clear the Zone Target cell."
            )

        mapping = ctx.protocol.scratch.get(ELECTRODE_TO_CHANNEL_KEY, {})
        channels = zone_detection_channels(regions, mapping)

        if not channels:
            raise RuntimeError(
                f"{step}: zone type {zone_id!r} has no region with a "
                "channel-mapped electrode to check."
            )

        detected = self._detect_droplets(channels, ctx, step)
        region = select_zone_region(regions, detected, criterion, mapping)
        checked = ", ".join(candidate["id"] for candidate in regions)

        if region is None:
            raise RuntimeError(
                f"{step}: no region of zone type {zone_id!r} meets "
                f"{criterion!r}. Checked in order: {checked}; droplets "
                f"detected on channels {sorted(detected)}."
            )

        logger.info(
            f"{step}: zone target {zone_id!r} ({criterion}) chose region "
            f"{region['id']} (checked in order: {checked}); actuating "
            f"{region['electrode_ids']}"
        )

        ctx.scratch[EXTRA_STATIC_ELECTRODES_KEY] = list(region["electrode_ids"])

        protocol_logging_data_contribution_publisher.publish(
            {
                "Zone Target": zone_id,
                "Zone Target Criterion": criterion,
                "Zone Target Region": region["id"],
            }
        )

    def _detect_droplets(self, channels, ctx, step):
        """Request detection on ``channels`` and return the detected ones."""

        if self.ack_time_s <= 0:
            raise RuntimeError(
                f"{step}: the Zone Target column needs the droplet-detection "
                "reply, but its ack wait is 0 s in Protocol Settings."
            )

        publish_message(topic=DETECT_DROPLETS, message=json.dumps(channels))

        reply = json.loads(ctx.wait_for(DROPLETS_DETECTED, timeout=self.ack_time_s))

        if not reply.get("success"):
            raise RuntimeError(
                f"{step}: droplet detection for the zone target failed: "
                f"{reply.get('error')}"
            )

        return [int(channel) for channel in reply.get("detected_channels", [])]


def make_zone_target_column():
    """Return a fresh Zone Target compound column (zone type + criterion)."""
    return CompoundColumn(
        model=ZoneTargetCompoundModel(),
        view=DictCompoundColumnView(
            cell_views={
                ZONE_TARGET_FIELD_ID: ZoneTypeComboBoxView(),
                ZONE_TARGET_CRITERION_FIELD_ID: ZoneCriterionComboBoxView(),
            }
        ),
        handler=ZoneTargetHandler(),
    )
