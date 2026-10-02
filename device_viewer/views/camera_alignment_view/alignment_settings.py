# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI model + view for the Camera Alignment dialog's
settings sidebar.

A Qt-free HasTraits model mirrors the persisted alignment
preference traits (snap radius, dot radius, frame width, the quad
colors and the corner-marker color/alpha) so the sidebar is a plain
TraitsUI View —
spinners from the Range traits, color wells from the RGBColor
traits, and a Reset to Defaults button — instead of hand-built Qt
widgets. Every model edit writes straight back to the preferences;
the dialog observes the model to restyle the overlays live."""

# Enthought library imports.
from traits.api import Button, HasTraits, Instance, Range, observe
from traitsui.api import Group, Item, RGBColor, View

# Microdrop utils imports.
from microdrop_utils.color_helpers import hex_to_rgb, rgb_to_hex

# Local imports.
from ...consts import (
    ALIGNMENT_ACTIVE_RING_SCALE_MAX,
    ALIGNMENT_ACTIVE_RING_SCALE_MIN,
    ALIGNMENT_FRAME_WIDTH_MAX_PX,
    ALIGNMENT_FRAME_WIDTH_MIN_PX,
    ALIGNMENT_HANDLE_RADIUS_MAX_PX,
    ALIGNMENT_HANDLE_RADIUS_MIN_PX,
    ALIGNMENT_SNAP_MARKER_SIZE_MAX_PX,
    ALIGNMENT_SNAP_MARKER_SIZE_MIN_PX,
    ALIGNMENT_SNAP_RADIUS_MAX_PX,
    ALIGNMENT_SNAP_RADIUS_MIN_PX,
)
from ...preferences import DeviceViewerPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


# The model's setting traits; each mirrors the preference trait named
# 'alignment_<name>', and the names double one-for-one as QuadOverlay
# kwargs (snap_radius_px directly, the rest via set_appearance) — so
# `{name: getattr(preferences, f"alignment_{name}") for name in
# SETTING_TRAITS}` is the full option dict a pane opens with.
NUMERIC_SETTING_TRAITS = (
    "snap_radius_px",
    "handle_radius_px",
    "frame_width_px",
    "snap_marker_alpha",
    "snap_marker_size_px",
    "active_alpha",
    "active_ring_scale",
    "number_alpha",
)
COLOR_SETTING_TRAITS = (
    "quad_color",
    "handle_color",
    "handle_ring_color",
    "snap_marker_color",
    "active_color",
)
SETTING_TRAITS = NUMERIC_SETTING_TRAITS + COLOR_SETTING_TRAITS


class AlignmentSettingsModel(HasTraits):
    """The sidebar's model. Bounds match the preference Range
    traits; values load from the preferences at construction and
    write back on every edit, so tuning persists like everything
    else."""

    preferences = Instance(DeviceViewerPreferences)

    snap_radius_px = Range(
        ALIGNMENT_SNAP_RADIUS_MIN_PX, ALIGNMENT_SNAP_RADIUS_MAX_PX, mode="spinner"
    )
    handle_radius_px = Range(
        ALIGNMENT_HANDLE_RADIUS_MIN_PX, ALIGNMENT_HANDLE_RADIUS_MAX_PX, mode="spinner"
    )
    frame_width_px = Range(
        ALIGNMENT_FRAME_WIDTH_MIN_PX, ALIGNMENT_FRAME_WIDTH_MAX_PX, mode="spinner"
    )

    #: Opacity and size of the view-all-snappable-corners dots.
    snap_marker_alpha = Range(0.0, 1.0)
    snap_marker_size_px = Range(
        ALIGNMENT_SNAP_MARKER_SIZE_MIN_PX,
        ALIGNMENT_SNAP_MARKER_SIZE_MAX_PX,
        mode="spinner",
    )

    #: Opacity and ring size (in dot radii) of the highlight on the dot
    #: hovered or pressed, which marks the matching dot in both panes.
    active_alpha = Range(0.0, 1.0)
    #: Opacity of the dot numbers (1-4); 0 hides them.
    number_alpha = Range(0.0, 1.0)

    active_ring_scale = Range(
        ALIGNMENT_ACTIVE_RING_SCALE_MIN, ALIGNMENT_ACTIVE_RING_SCALE_MAX
    )

    quad_color = RGBColor()
    handle_color = RGBColor()
    handle_ring_color = RGBColor()
    snap_marker_color = RGBColor()
    active_color = RGBColor()

    reset = Button("Reset to Defaults")

    def traits_init(self):
        self._sync_from_preferences()

    # ------------------------------------------------------------------ #
    def _sync_from_preferences(self):
        preferences = self.preferences

        self.trait_set(
            **{
                name: getattr(preferences, f"alignment_{name}")
                for name in NUMERIC_SETTING_TRAITS
            },
            **{
                name: hex_to_rgb(getattr(preferences, f"alignment_{name}"))
                for name in COLOR_SETTING_TRAITS
            },
        )

    @observe(", ".join(SETTING_TRAITS))
    def _setting_changed(self, event):
        """Write every edit straight back to the matching
        'alignment_' preference (colors as hex)."""
        value = event.new

        if event.name in COLOR_SETTING_TRAITS:
            value = rgb_to_hex(value)

        self.preferences.trait_set(**{f"alignment_{event.name}": value})

    def _reset_fired(self):
        """Put the built-in defaults back: reset the preference
        traits, then resync — the resulting model-trait changes
        notify the dialog so the overlays follow live."""
        self.preferences.reset_traits([f"alignment_{name}" for name in SETTING_TRAITS])

        self._sync_from_preferences()


alignment_settings_view = View(
    Group(
        Item("snap_radius_px", label="Snap radius (px)"),
        Item("handle_radius_px", label="Dot radius (px)"),
        Item("frame_width_px", label="Frame width (px)"),
        Item("quad_color", label="Frame color"),
        Item("handle_color", label="Dot color"),
        Item("handle_ring_color", label="Dot ring color"),
        Item("snap_marker_color", label="Corner marker color"),
        Item("snap_marker_alpha", label="Corner marker alpha"),
        Item("snap_marker_size_px", label="Corner marker size (px)"),
        Item("active_color", label="Highlight color"),
        Item("active_alpha", label="Highlight alpha"),
        Item("active_ring_scale", label="Highlight size (x dot)"),
        Item("number_alpha", label="Number alpha"),
        label="Overlay Settings",
        show_border=True,
    ),
    Item("reset", show_label=False),
    resizable=True,
)
