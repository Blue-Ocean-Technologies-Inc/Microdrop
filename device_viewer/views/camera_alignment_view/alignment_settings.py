"""TraitsUI model + view for the Camera Alignment dialog's
settings sidebar.

A Qt-free HasTraits model mirrors the seven persisted alignment
preference traits (per-pane snap radii, dot radius, frame width and
the three quad colors) so the sidebar is a plain TraitsUI View —
spinners from the Range traits, color wells from the RGBColor
traits, and a Reset to Defaults button — instead of hand-built Qt
widgets. Every model edit writes straight back to the preferences;
the dialog observes the model to restyle the overlays live."""

from traits.api import Button, HasTraits, Instance, Range, observe
from traitsui.api import Group, Item, RGBColor, View

from logger.logger_service import get_logger
from microdrop_utils.color_helpers import hex_to_rgb, rgb_to_hex

from ...consts import (
    ALIGNMENT_FRAME_WIDTH_MAX_PX,
    ALIGNMENT_FRAME_WIDTH_MIN_PX,
    ALIGNMENT_HANDLE_RADIUS_MAX_PX,
    ALIGNMENT_HANDLE_RADIUS_MIN_PX,
    ALIGNMENT_SNAP_RADIUS_MAX_PX,
    ALIGNMENT_SNAP_RADIUS_MIN_PX,
)
from ...preferences import DeviceViewerPreferences

logger = get_logger(__name__)


# The model's setting traits; each mirrors the preference trait named
# 'alignment_<name>'. All double as QuadOverlay kwargs (the numeric
# snap radii per pane, the rest via set_appearance).
NUMERIC_SETTING_TRAITS = (
    "endpoint_snap_radius_px",
    "outline_snap_radius_px",
    "handle_radius_px",
    "frame_width_px",
)
COLOR_SETTING_TRAITS = (
    "quad_color",
    "handle_color",
    "handle_ring_color",
)
SETTING_TRAITS = NUMERIC_SETTING_TRAITS + COLOR_SETTING_TRAITS


def overlay_options_from_preferences(preferences, snap_radius_trait) -> dict:
    """The QuadOverlay kwargs a pane should open with, read from
    the persisted preferences; ``snap_radius_trait`` names the
    pane's own snap-radius preference."""
    return {
        "snap_radius_px": getattr(preferences, snap_radius_trait),
        "handle_radius_px": preferences.alignment_handle_radius_px,
        "frame_width_px": preferences.alignment_frame_width_px,
        "quad_color": preferences.alignment_quad_color,
        "handle_color": preferences.alignment_handle_color,
        "handle_ring_color": preferences.alignment_handle_ring_color,
    }


class AlignmentSettingsModel(HasTraits):
    """The sidebar's model. Bounds match the preference Range
    traits; values load from the preferences at construction and
    write back on every edit, so tuning persists like everything
    else."""

    preferences = Instance(DeviceViewerPreferences)

    endpoint_snap_radius_px = Range(
        ALIGNMENT_SNAP_RADIUS_MIN_PX, ALIGNMENT_SNAP_RADIUS_MAX_PX, mode="spinner"
    )
    outline_snap_radius_px = Range(
        ALIGNMENT_SNAP_RADIUS_MIN_PX, ALIGNMENT_SNAP_RADIUS_MAX_PX, mode="spinner"
    )
    handle_radius_px = Range(
        ALIGNMENT_HANDLE_RADIUS_MIN_PX, ALIGNMENT_HANDLE_RADIUS_MAX_PX, mode="spinner"
    )
    frame_width_px = Range(
        ALIGNMENT_FRAME_WIDTH_MIN_PX, ALIGNMENT_FRAME_WIDTH_MAX_PX, mode="spinner"
    )

    quad_color = RGBColor()
    handle_color = RGBColor()
    handle_ring_color = RGBColor()

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
        Item("endpoint_snap_radius_px", label="Endpoint (px)"),
        Item("outline_snap_radius_px", label="Outline (px)"),
        label="Snap Radius",
        show_border=True,
    ),
    Group(
        Item("handle_radius_px", label="Dot radius (px)"),
        Item("frame_width_px", label="Frame width (px)"),
        Item("quad_color", label="Frame color"),
        Item("handle_color", label="Dot color"),
        Item("handle_ring_color", label="Dot ring color"),
        label="Quad Appearance",
        show_border=True,
    ),
    Item("reset", show_label=False),
    resizable=True,
)
