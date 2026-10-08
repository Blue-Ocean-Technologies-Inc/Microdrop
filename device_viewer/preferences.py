# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import filecmp
from pathlib import Path

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from traits.api import (
    Bool,
    Dict,
    Directory,
    File,
    Float,
    Property,
    Range,
    Str,
)
from traits.etsconfig.api import ETSConfig
from traitsui.api import FileEditor, Group, Item, View

# Microdrop package imports.
from microdrop_application.preferences_dialog import advanced_mode_tab

# Microdrop style imports.
from microdrop_style.text_styles import preferences_group_style_sheet

# Microdrop utils imports.
from microdrop_utils.file_handler import safe_copy_file
from microdrop_utils.preferences_UI_helpers import (
    create_grid_group,
    create_item_label_group,
    create_item_label_pair,
)

# Local imports.
from .consts import (
    ALIGNMENT_ACTIVE_ALPHA,
    ALIGNMENT_ACTIVE_COLOR_HEX,
    ALIGNMENT_ACTIVE_RING_SCALE,
    ALIGNMENT_ACTIVE_RING_SCALE_MAX,
    ALIGNMENT_ACTIVE_RING_SCALE_MIN,
    ALIGNMENT_FRAME_WIDTH_MAX_PX,
    ALIGNMENT_FRAME_WIDTH_MIN_PX,
    ALIGNMENT_FRAME_WIDTH_PX,
    ALIGNMENT_HANDLE_COLOR_HEX,
    ALIGNMENT_HANDLE_RADIUS_MAX_PX,
    ALIGNMENT_HANDLE_RADIUS_MIN_PX,
    ALIGNMENT_HANDLE_RADIUS_PX,
    ALIGNMENT_HANDLE_RING_COLOR_HEX,
    ALIGNMENT_NUMBER_ALPHA,
    ALIGNMENT_QUAD_COLOR_HEX,
    ALIGNMENT_SNAP_MARKER_ALPHA,
    ALIGNMENT_SNAP_MARKER_COLOR_HEX,
    ALIGNMENT_SNAP_MARKER_SIZE_MAX_PX,
    ALIGNMENT_SNAP_MARKER_SIZE_MIN_PX,
    ALIGNMENT_SNAP_MARKER_SIZE_PX,
    ALIGNMENT_SNAP_RADIUS_MAX_PX,
    ALIGNMENT_SNAP_RADIUS_MIN_PX,
    ALIGNMENT_SNAP_RADIUS_PX,
    ALPHA_VIEW_MIN_HEIGHT,
    AUTO_FIT_MARGIN_SCALE,
    DEVICE_VIEWER_SIDEBAR_WIDTH,
    LAYERS_VIEW_MIN_HEIGHT,
    MASTER_SVG_FILE,
    MAX_SLUG_WIDTH,
    NUMBER_OF_CHANNELS,
    PIN_MAP_SVG_FILE,
    ZONES_VIEW_MIN_HEIGHT,
    ZOOM_SENSITIVITY,
)
from .default_settings import default_alphas, default_visibility

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class DeviceViewerPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.device_viewer"

    #### Preferences ##########################################################
    ### Side bar prefs ###
    DEVICE_VIEWER_SIDEBAR_WIDTH = Range(
        value=DEVICE_VIEWER_SIDEBAR_WIDTH, low=0, high=10000
    )
    ALPHA_VIEW_MIN_HEIGHT = Range(value=ALPHA_VIEW_MIN_HEIGHT, low=0, high=10000)
    LAYERS_VIEW_MIN_HEIGHT = Range(value=LAYERS_VIEW_MIN_HEIGHT, low=0, high=10000)
    ZONES_VIEW_MIN_HEIGHT = Range(value=ZONES_VIEW_MIN_HEIGHT, low=0, high=10000)

    default_visibility = Dict(default_visibility)
    default_alphas = Dict(default_alphas)

    #: Zone types shared across devices: zone id -> display name / hex color.
    #: Mirrored from ZoneLayerManager.zone_types by DeviceViewMainModel.
    zone_type_names = Dict(Str, Str)
    zone_type_colors = Dict(Str, Str)

    ### Camera-alignment dialog prefs ###
    # One snap radius shared by both panes. Colors are stored as
    # '#rrggbb' hex strings.
    alignment_snap_radius_px = Range(
        value=ALIGNMENT_SNAP_RADIUS_PX,
        low=ALIGNMENT_SNAP_RADIUS_MIN_PX,
        high=ALIGNMENT_SNAP_RADIUS_MAX_PX,
        mode="spinner",
    )
    alignment_handle_radius_px = Range(
        value=ALIGNMENT_HANDLE_RADIUS_PX,
        low=ALIGNMENT_HANDLE_RADIUS_MIN_PX,
        high=ALIGNMENT_HANDLE_RADIUS_MAX_PX,
        mode="spinner",
    )
    alignment_frame_width_px = Range(
        value=ALIGNMENT_FRAME_WIDTH_PX,
        low=ALIGNMENT_FRAME_WIDTH_MIN_PX,
        high=ALIGNMENT_FRAME_WIDTH_MAX_PX,
        mode="spinner",
    )
    alignment_quad_color = Str(ALIGNMENT_QUAD_COLOR_HEX)
    alignment_handle_color = Str(ALIGNMENT_HANDLE_COLOR_HEX)
    alignment_handle_ring_color = Str(ALIGNMENT_HANDLE_RING_COLOR_HEX)
    alignment_snap_marker_color = Str(ALIGNMENT_SNAP_MARKER_COLOR_HEX)
    alignment_snap_marker_alpha = Range(
        value=ALIGNMENT_SNAP_MARKER_ALPHA, low=0.0, high=1.0
    )
    alignment_snap_marker_size_px = Range(
        value=ALIGNMENT_SNAP_MARKER_SIZE_PX,
        low=ALIGNMENT_SNAP_MARKER_SIZE_MIN_PX,
        high=ALIGNMENT_SNAP_MARKER_SIZE_MAX_PX,
        mode="spinner",
    )
    alignment_active_color = Str(ALIGNMENT_ACTIVE_COLOR_HEX)
    alignment_active_alpha = Range(value=ALIGNMENT_ACTIVE_ALPHA, low=0.0, high=1.0)
    alignment_active_ring_scale = Range(
        value=ALIGNMENT_ACTIVE_RING_SCALE,
        low=ALIGNMENT_ACTIVE_RING_SCALE_MIN,
        high=ALIGNMENT_ACTIVE_RING_SCALE_MAX,
    )
    alignment_number_alpha = Range(value=ALIGNMENT_NUMBER_ALPHA, low=0.0, high=1.0)

    ### Recording viewer (video_viewer pane) prefs ###
    # Persisted zoom/pan of the playback canvas — the alignment transform
    # can push the frame outside the pane's bounds, so the user's chosen
    # framing must survive reloads. zoom 0.0 = unset (fit to view).
    video_viewer_zoom = Float(0.0)
    video_viewer_center_x = Float(0.0)
    video_viewer_center_y = Float(0.0)

    ### main view prefs ###
    AUTO_FIT_MARGIN_SCALE = Range(
        value=AUTO_FIT_MARGIN_SCALE, low=1, high=100, mode="spinner"
    )
    ZOOM_SENSITIVITY = Range(value=ZOOM_SENSITIVITY, low=1, high=100, mode="spinner")

    # Number of electrode channels (valid channel indices 0 to NUMBER_OF_CHANNELS - 1)
    NUMBER_OF_CHANNELS = Range(
        value=NUMBER_OF_CHANNELS, low=1, high=1024, mode="spinner"
    )

    # Widest slug the route sidebar's lane sliders allow, route electrode
    # included.
    max_slug_width = Range(value=MAX_SLUG_WIDTH, low=1, high=21, mode="spinner")

    # getters for processed values from int set in spinner
    _auto_fit_margin_scale = Property(observe="AUTO_FIT_MARGIN_SCALE")
    _zoom_scale = Property(observe="ZOOM_SENSITIVITY")

    DEFAULT_SVG_FILE = File

    DEVICE_REPO_DIR = Directory()

    def _DEVICE_REPO_DIR_default(self) -> Path:
        default_dir = Path(ETSConfig.user_data) / "Devices"

        default_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Default repo directory is: {default_dir}")

        # Seed the repo with the bundled device files on first run. Only copy a
        # file that is missing so user-modified copies are never clobbered.
        for source_file in (MASTER_SVG_FILE, PIN_MAP_SVG_FILE):
            destination = default_dir / source_file.name
            if not destination.exists():
                if source_file.exists():
                    logger.info(
                        f"Missing {source_file.name} in device repo.\n"
                        f"Copying {source_file} to {destination}"
                    )
                    safe_copy_file(str(source_file), str(destination))
                else:
                    logger.error(f"Bundled device file not found: {source_file}")

        return default_dir

    def _DEFAULT_SVG_FILE_default(self):
        # --- Define Master File Path (local to the script) ---
        logger.debug(f"Master default device svg is located at: {MASTER_SVG_FILE}")

        if not MASTER_SVG_FILE.exists():
            logger.error("Master default device svg not found!.")
            raise FileNotFoundError("Master default device svg not found!.")

        # --- Ensure User's File is a Copy of Master on First Run ---
        default_user_file = Path(self.DEVICE_REPO_DIR) / MASTER_SVG_FILE.name
        logger.debug(
            f"Checking for user's default device svg file: {default_user_file}"
        )

        should_overwrite = True

        if default_user_file.exists():
            # If the user's file exists, check if it's different from master

            if filecmp.cmp(MASTER_SVG_FILE, default_user_file, shallow=False):
                logger.info(
                    "User's default device svg file already exists and matches master."
                )
                should_overwrite = False

            else:
                logger.info(
                    "User's default device svg file exists but is different "
                    "from master. Overwriting..."
                )

        else:
            logger.info(
                "User's default device svg file not found, creating it from master..."
            )

        if should_overwrite:
            default_user_file = safe_copy_file(
                str(MASTER_SVG_FILE), str(default_user_file)
            )

        return str(default_user_file)

    def _get__auto_fit_margin_scale(self) -> float:
        return self.AUTO_FIT_MARGIN_SCALE / 100

    def _get__zoom_scale(self) -> float:
        return 1 + (self.ZOOM_SENSITIVITY / 100)


device_viewer_tab = PreferencesCategory(
    id="microdrop.device_viewer.preferences",
    name="Device Viewer",
)

# Define device viewer preferences pane view contents

# This is the list of trait names for the grid layout
sidebar_setting_items = [
    "DEVICE_VIEWER_SIDEBAR_WIDTH",
    "ALPHA_VIEW_MIN_HEIGHT",
    "LAYERS_VIEW_MIN_HEIGHT",
    "ZONES_VIEW_MIN_HEIGHT",
]

# Create the grid group for the sidebar items.
sidebar_settings_grid = create_grid_group(
    sidebar_setting_items,
    group_label="Sidebar View",
    group_show_border=True,  # Example of passing a group kwarg
    group_style_sheet=preferences_group_style_sheet,
)

########## Main view grid ###########################
# Create items for the default svg for the main view group.
default_svg_setting_item = create_item_label_pair(
    "DEFAULT_SVG_FILE",
    label_text="Default Device Layout",
    item_editor=FileEditor(
        filter=["SVG Files (*.svg)|*.svg|All Files (*.*)|*.*"], dialog_style="open"
    ),
)

default_auto_fit_margin_scale_item = create_item_label_group(
    "AUTO_FIT_MARGIN_SCALE",
)

default_zoom_sensitivity = create_item_label_group(
    "ZOOM_SENSITIVITY",
)

default_number_of_channels = create_item_label_group(
    "NUMBER_OF_CHANNELS",
    label_text="Number of channels",
)

main_view_settings = (
    Group(
        [
            default_svg_setting_item,
            default_auto_fit_margin_scale_item,
            default_zoom_sensitivity,
            default_number_of_channels,
        ],
        label="Main View",
        show_labels=False,
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    ),
)


########## Path settings ###########################
path_settings = Group(
    create_item_label_group(
        "max_slug_width",
        label_text="Max slug width (electrodes)",
        item_tooltip="The widest slug the route sidebar allows, route electrode "
        "included: the two lane counts add up to at most one less.",
    ),
    label="Paths",
    show_labels=False,
    show_border=True,
    style_sheet=preferences_group_style_sheet,
)


class DeviceViewerPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane.

    Based on the preferences pane of the envisage Attractors example.
    """

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = DeviceViewerPreferences

    category = device_viewer_tab.id

    ########################################################################################

    view = View(
        Item("_"),  # Separator
        main_view_settings,
        Item("_"),  # Separator
        sidebar_settings_grid,
        Item("_"),  # Separator
        path_settings,
        Item("_"),  # Separator
        resizable=True,
    )


#### Advanced Mode preferences (shown only when Advanced Mode is enabled)


class DeviceViewerAdvancedPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.device_viewer.advanced"

    #### Preferences ##########################################################
    allow_hardware_disables = Bool(True)


class DeviceViewerAdvancedPreferencesPane(PreferencesPane):
    """Advanced mode preferences pane. Only visible when Advanced Mode is toggled on."""

    model_factory = DeviceViewerAdvancedPreferences

    category = advanced_mode_tab.id

    view = View(
        Item("_"),  # Separator
        Group(
            Item(
                "allow_hardware_disables",
                tooltip=(
                    "When enabled, the device viewer will visually reflect "
                    "channels that the hardware has reported as disabled (e.g., "
                    "due to detected shorts or actuation faults). Disabled "
                    "channels will appear greyed out and non-interactive in the "
                    "device view.\n\n"
                    "When disabled, hardware-reported channel disables are "
                    "ignored by the device viewer and all channels remain "
                    "visually active regardless of hardware state.\n\n"
                    "WARNING: Disabling this setting means you will NOT see "
                    "visual feedback when the hardware disables channels for "
                    "safety reasons. Only change this if you understand the "
                    "implications for your experiment."
                ),
            ),
            label="Device Viewer",
            show_border=True,
            style_sheet=preferences_group_style_sheet,
        ),
        Item("_"),
        resizable=True,
    )
