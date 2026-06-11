"""Hidden trail-overlay column. How many electrodes the current and
next windows share — controls the effective step size.

Bounds mirror the DV sidebar's RouteLayerManager: overlay can never
reach trail_length (overlapping every electrode would mean no movement
between phases), so the effective maximum is ``trail_length - 1`` —
enforced dynamically by the editor and clamped by the handler. The
pane's cell-change clamp drags overlay down when Trail Len shrinks.
"""

from traits.api import Int

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenIntSpinBoxColumnView,
)


class TrailOverlayColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(int(self.default_value or 0),
                   desc="Electrodes shared between the current and "
                        "next windows. step_size = max(1, length - overlay).")


class TrailOverlayColumnView(HiddenIntSpinBoxColumnView):
    """Spinbox maximum follows the row's trail_length (the DV sidebar's
    dynamic ``max_trail_overlay = trail_length - 1`` Range bound)."""

    def create_editor(self, parent, context):
        editor = super().create_editor(parent, context)
        if context is not None:
            trail_length = int(getattr(context, "trail_length", 1) or 1)
            editor.setMaximum(max(0, min(self.high, trail_length - 1)))
        return editor


class TrailOverlayHandler(BaseColumnHandler):
    """Clamp writes to ``trail_length - 1`` — covers paths that bypass
    the editor bound (stale editors, programmatic on_interact calls)."""

    def on_interact(self, row, model, value):
        max_overlay = max(0, int(getattr(row, "trail_length", 1) or 1) - 1)
        return model.set_value(row, min(int(value or 0), max_overlay))


def make_trail_overlay_column():
    return Column(
        model=TrailOverlayColumnModel(
            col_id="trail_overlay", col_name="Trail Overlay", default_value=0,
        ),
        view=TrailOverlayColumnView(low=0, high=10000),
        handler=TrailOverlayHandler(),
    )
