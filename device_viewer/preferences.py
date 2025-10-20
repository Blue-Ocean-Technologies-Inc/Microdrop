from pathlib import Path
import filecmp

from apptools.preferences.api import PreferencesHelper
from traits.api import File, Range, Directory, Dict
from traits.etsconfig.api import ETSConfig
from traitsui.api import VGroup, View, Item, FileEditor
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_utils.preferences_UI_helpers import create_grid_group, create_item_label_group
from microdrop_utils.file_handler import safe_copy_file
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

from microdrop_style.text_styles import preferences_group_style_sheet

from .consts import DEVICE_VIEWER_SIDEBAR_WIDTH, ALPHA_VIEW_MIN_HEIGHT, LAYERS_VIEW_MIN_HEIGHT, MASTER_SVG_FILE
from .default_settings import default_alphas, default_visibility


class DeviceViewerPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.device_viewer"

    #### Preferences ##########################################################
    DEVICE_VIEWER_SIDEBAR_WIDTH = Range(value=DEVICE_VIEWER_SIDEBAR_WIDTH, low=0, high=10000)
    ALPHA_VIEW_MIN_HEIGHT = Range(value=ALPHA_VIEW_MIN_HEIGHT, low=0, high=10000)
    LAYERS_VIEW_MIN_HEIGHT = Range(value=LAYERS_VIEW_MIN_HEIGHT, low=0, high=10000)

    default_visibility = Dict(default_visibility)
    default_alphas = Dict(default_alphas)

    DEFAULT_SVG_FILE = File

    DEVICE_REPO_DIR = Directory()

    def _DEVICE_REPO_DIR_default(self) -> Path:
        default_dir = Path(ETSConfig.user_data) / "Devices"

        default_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Default repo directory is: {default_dir}")

        return default_dir

    def _DEFAULT_SVG_FILE_default(self):
        # --- Define Master File Path (local to the script) ---
        logger.debug(f"Master svg file is located at: {MASTER_SVG_FILE}")

        if not MASTER_SVG_FILE.exists():
            logger.error("Master file not found!.")
            raise FileNotFoundError("Master file not found!.")

        # --- Ensure User's File is a Copy of Master on First Run ---
        default_user_file = Path(self.DEVICE_REPO_DIR) / MASTER_SVG_FILE.name
        logger.debug(f"Checking for user's default file: {default_user_file}")

        should_overwrite = True

        if default_user_file.exists():
            # If the user's file exists, check if it's different from master

            if filecmp.cmp(MASTER_SVG_FILE, default_user_file, shallow=False):
                logger.info("User's file already exists and matches master.")
                should_overwrite = False

            else:
                logger.info("User's default svg file exists but is different from master. Overwriting...")

        else:
            logger.info("User's default svg file not found, creating it from master...")

        if should_overwrite:
            default_user_file = safe_copy_file(str(MASTER_SVG_FILE), str(default_user_file))

        return str(default_user_file)


device_viewer_tab = PreferencesCategory(
    id="microdrop.device_viewer.preferences",
    name="Device Viewer",
)


class DeviceViewerPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = DeviceViewerPreferences

    category = device_viewer_tab.id

    #### 'DeviceViewerPreferencesPane' interface ################################

    # This is the list of trait names for the grid layout
    sidebar_setting_items = [
        'DEVICE_VIEWER_SIDEBAR_WIDTH',
        'ALPHA_VIEW_MIN_HEIGHT',
        'LAYERS_VIEW_MIN_HEIGHT',
    ]

    # Create the grid group for the sidebar items.
    sidebar_settings_grid = create_grid_group(
        sidebar_setting_items,
        group_label="Sidebar View",
        group_show_border=True,  # Example of passing a group kwarg
        group_style_sheet=preferences_group_style_sheet,
    )

    # Create the single item for the default svg for the main view group.
    default_svg_setting_group = create_item_label_group(
            'DEFAULT_SVG_FILE',
            label_text='Default Device Layout',
            item_editor=FileEditor(
                filter=['SVG Files (*.svg)|*.svg|All Files (*.*)|*.*'],
                dialog_style='open'
            ),
        )

    main_view_settings = VGroup(
        default_svg_setting_group,
        label="Main View",
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    ),

    view = View(

        Item("_"),  # Separator

        main_view_settings,

        Item("_"),  # Separator

        sidebar_settings_grid,

        Item("_"),  # Separator to space this out from further contributions to the pane.

        resizable=True
    )
