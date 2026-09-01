# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Magnet compound column — drives the portable instrument's magnet Z
motor for an experiment step. Three coupled cells (set_magnet Bool +
magnet_on Bool + magnet_height_mm Float) sharing one model + one handler
via the PPT-11 compound framework.

set_magnet unchecked = the step leaves the magnet untouched (no
engage/disengage publish, no applied-ack wait).

Sentinel value MAGNET_HEIGHT_MM_BOUNDS[0] - 0.5 represents 'Default'
mode — the spinbox renders it as 'Default' (Qt's setSpecialValueText)
and the backend reads it as "run the firmware's engage macro" rather
than an absolute Z position. A non-sentinel height is an absolute
position on the magnet Z motor (mm), driven straight through
motorAbsoluteMove.
"""

# Standard library imports.
import json

# Enthought library imports.
from pyface.qt.QtCore import Qt
from traits.api import Bool, Float

# Microdrop package imports.
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
    BaseCompoundColumnModel,
    CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)
from portable_dropbot_controller.consts import (
    MAGNET_APPLIED,
    MAGNET_HEIGHT_MM_BOUNDS,
    PROTOCOL_SET_MAGNET,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import SET_MAGNET_FIELD_ID

# Sentinel value below the minimum hardware position; the spinbox
# renders it as "Default" and the backend treats any value below the
# minimum as "run the firmware's engage macro".
_DEFAULT_SENTINEL = float(MAGNET_HEIGHT_MM_BOUNDS[0] - 0.5)


class MagnetCompoundModel(BaseCompoundColumnModel):
    """Three coupled fields. base_id 'magnet' appears as compound_id on
    each field's column entry in JSON (PPT-11 framework)."""

    base_id = "magnet"

    def field_specs(self):
        return [
            FieldSpec(SET_MAGNET_FIELD_ID, "Set Magnet", False),
            FieldSpec("magnet_on", "Magnet", False),
            FieldSpec("magnet_height_mm", "Magnet Height (mm)", _DEFAULT_SENTINEL),
        ]

    def trait_for_field(self, field_id):
        if field_id == SET_MAGNET_FIELD_ID:
            return Bool(False)
        if field_id == "magnet_on":
            return Bool(False)
        if field_id == "magnet_height_mm":
            return Float(_DEFAULT_SENTINEL)
        raise KeyError(field_id)


class MagnetOnCheckboxView(CheckboxColumnView):
    """Engage/disengage checkbox, checkable only while the step's Set
    Magnet checkbox is on (cross-cell editability via the canonical
    PPT-11 get_flags(row) pattern)."""

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, SET_MAGNET_FIELD_ID, False):
            flags &= ~Qt.ItemIsUserCheckable
        return flags


class MagnetHeightSpinBoxView(DoubleSpinBoxColumnView):
    """Spinbox that displays the sentinel as 'Default' (via Qt's
    setSpecialValueText) and is read-only unless the step's Set Magnet
    checkbox is on and the magnet is engaged (cross-cell editability
    via the canonical PPT-11 get_flags(row) pattern)."""

    def create_editor(self, parent, context):
        e = super().create_editor(parent, context)
        e.setSpecialValueText("Default")
        return e

    def format_display(self, value, row):
        # Sentinel range matches the backend's threshold: any value
        # below MAGNET_HEIGHT_MM_BOUNDS[0] is interpreted as "Default"
        # (run the engage macro). Keeps the cell display + backend
        # semantics aligned.
        if value < MAGNET_HEIGHT_MM_BOUNDS[0]:
            return "Default"
        return super().format_display(value, row)

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not (
            getattr(row, SET_MAGNET_FIELD_ID, False)
            and getattr(row, "magnet_on", False)
        ):
            flags &= ~Qt.ItemIsEditable
        return flags


class MagnetHandler(BaseCompoundColumnHandler):
    """Publishes the row's magnet state and waits for the ack.

    Priority 20 — parallel with the other portable protocol-step
    handlers in the same bucket; runs strictly before route handlers at
    priority 30. The ack wait comes from the Protocol Settings grid;
    set it to 0 there to run fire-and-forget without a magnet
    responder.

    No on_interact override — the magnet column does not persist
    user cell-edits to any preferences object. The portable has no
    z-stage up-height preference; "Default" always means the firmware's
    engage macro.
    """

    priority = 20
    wait_for_topics = [MAGNET_APPLIED]
    # Provider default for the Protocol Settings ack-wait grid: the
    # portable's magnet Z move blocks up to ~30 s in the driver, so this
    # needs real headroom beyond the RPC round-trip.
    default_ack_time_s = 40.0

    def on_step(self, row, ctx):
        # Preview mode: skip the hardware-publish + ack-wait. The
        # magnet doesn't move and no MAGNET_APPLIED comes back. Mirrors
        # the legacy protocol_grid Preview Mode.
        if getattr(ctx.protocol, "preview_mode", False):
            return
        # Unchecked = the step leaves the magnet untouched: no
        # engage/disengage publish, no applied-ack wait.
        if not getattr(row, SET_MAGNET_FIELD_ID, False):
            return
        payload = json.dumps(
            {"on": bool(row.magnet_on), "height_mm": float(row.magnet_height_mm)}
        )
        publish_message(topic=PROTOCOL_SET_MAGNET, message=payload)

        if self.ack_time_s > 0:
            ctx.wait_for(MAGNET_APPLIED, timeout=self.ack_time_s)


def make_magnet_column():
    """Factory — returns a fresh CompoundColumn with MagnetHandler for
    publishing magnet state and waiting for acknowledgement."""
    return CompoundColumn(
        model=MagnetCompoundModel(),
        view=DictCompoundColumnView(
            cell_views={
                SET_MAGNET_FIELD_ID: CheckboxColumnView(),
                "magnet_on": MagnetOnCheckboxView(),
                "magnet_height_mm": MagnetHeightSpinBoxView(
                    low=_DEFAULT_SENTINEL,
                    high=float(MAGNET_HEIGHT_MM_BOUNDS[1]),
                    decimals=2,
                    single_step=0.1,
                ),
            }
        ),
        handler=MagnetHandler(),
    )
