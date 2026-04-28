"""Magnet compound column — engages/retracts the peripheral z-stage
for an experiment step. Two coupled cells (magnet_on Bool + magnet_height_mm
Float) sharing one model + one handler via the PPT-11 compound framework.

Sentinel value MIN_ZSTAGE_HEIGHT_MM - 0.5 (= 0.0) represents 'Default'
mode — the spinbox renders it as 'Default' (Qt's setSpecialValueText)
and the backend reads PeripheralPreferences().up_height_mm at runtime
when it sees a sub-MIN value. Preserves legacy behaviour where pref
changes affect 'Default' steps without re-editing the protocol.
"""

import json

from pyface.qt.QtCore import Qt
from traits.api import Bool, Float

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from peripheral_controller.consts import (
    MAX_ZSTAGE_HEIGHT_MM, MIN_ZSTAGE_HEIGHT_MM,
    PROTOCOL_SET_MAGNET, MAGNET_APPLIED,
)
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)


# Sentinel value below the minimum hardware position; the spinbox
# renders it as "Default" and the backend treats any value < MIN as
# "use the user's live up_height_mm pref".
_DEFAULT_SENTINEL = float(MIN_ZSTAGE_HEIGHT_MM - 0.5)


class MagnetCompoundModel(BaseCompoundColumnModel):
    """Two coupled fields. base_id 'magnet' appears as compound_id on
    each field's column entry in JSON (PPT-11 framework)."""
    base_id = "magnet"

    def field_specs(self):
        return [
            FieldSpec("magnet_on", "Magnet", False),
            FieldSpec("magnet_height_mm", "Magnet Height (mm)",
                      _DEFAULT_SENTINEL),
        ]

    def trait_for_field(self, field_id):
        if field_id == "magnet_on":
            return Bool(False)
        if field_id == "magnet_height_mm":
            return Float(_DEFAULT_SENTINEL)
        raise KeyError(field_id)


class MagnetHeightSpinBoxView(DoubleSpinBoxColumnView):
    """Spinbox that displays the sentinel as 'Default' (legacy parity
    via Qt.setSpecialValueText) and is read-only when row.magnet_on is
    False (cross-cell editability via the canonical PPT-11
    get_flags(row) pattern)."""

    def create_editor(self, parent, context):
        e = super().create_editor(parent, context)
        e.setSpecialValueText("Default")
        return e

    def format_display(self, value, row):
        # Sentinel range matches the backend's threshold: any value
        # below MIN_ZSTAGE_HEIGHT_MM is interpreted as "Default" (use
        # live pref). Keeps the cell display + backend semantics aligned.
        if value < MIN_ZSTAGE_HEIGHT_MM:
            return "Default"
        return super().format_display(value, row)

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "magnet_on", False):
            flags &= ~Qt.ItemIsEditable
        return flags


class MagnetHandler(BaseCompoundColumnHandler):
    """Publishes the row's magnet state and waits for the dropbot ack.

    Priority 20 — parallel with VoltageHandler / FrequencyHandler in the
    same bucket; runs strictly before RoutesHandler at priority 30. The
    10s timeout is longer than v/f's 5s because physical magnet
    movement is slower than RPC writes.

    No on_interact override — magnet column does NOT persist user
    cell-edits to PeripheralPreferences. The user changes up_height_mm
    via the peripherals_ui status panel, not via protocol cells.
    """
    priority = 20
    wait_for_topics = [MAGNET_APPLIED]

    def on_step(self, row, ctx):
        payload = json.dumps({
            "on": bool(row.magnet_on),
            "height_mm": float(row.magnet_height_mm),
        })
        publish_message(topic=PROTOCOL_SET_MAGNET, message=payload)
        ctx.wait_for(MAGNET_APPLIED, timeout=10.0)


def make_magnet_column():
    """Factory — returns a fresh CompoundColumn with MagnetHandler for
    publishing magnet state and waiting for acknowledgement."""
    return CompoundColumn(
        model=MagnetCompoundModel(),
        view=DictCompoundColumnView(cell_views={
            "magnet_on": CheckboxColumnView(),
            "magnet_height_mm": MagnetHeightSpinBoxView(
                low=_DEFAULT_SENTINEL,
                high=float(MAX_ZSTAGE_HEIGHT_MM),
                decimals=2, single_step=0.1,
            ),
        }),
        handler=MagnetHandler(),
    )
