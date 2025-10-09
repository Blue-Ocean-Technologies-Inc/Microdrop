from pathlib import Path

from apptools.preferences.api import PreferencesHelper
from traits.api import Int, File, Range
from traitsui.api import VGroup, View, spring, Item, FileEditor
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_utils.preferences_UI_helpers import create_grid_group, create_labeled_group

from .consts import DEVICE_VIEWER_SIDEBAR_WIDTH, ALPHA_VIEW_MIN_HEIGHT, LAYERS_VIEW_MIN_HEIGHT, preferences_group_style_sheet


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
    DEFAULT_SVG_FILE = File

    def _DEFAULT_SVG_FILE_default(self):
        return Path(__file__).parent /  "90_pin_array.svg"

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

    #### 'AttractorsPreferencesPane' interface ################################

    # Assume the following imports are present:
    # from traitsui.api import View, VGroup, Item, FileEditor
    # from traits_ui_helpers import create_labeled_group, create_grid_group

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

    # Create the single item for the default layout.
    # The 'editor' kwarg is passed directly to the Item

    default_svg_setting_group = create_labeled_group(
            'DEFAULT_SVG_FILE',
            label_text='Default Device Layout',
            item_editor=FileEditor(
                filter=['SVG Files (*.svg)|*.svg|All Files (*.*)|*.*'],
                dialog_style='open'
            ),
            group_show_labels=True,
        )

    main_view_settings = VGroup(
        default_svg_setting_group,
        label="Main View",
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    ),

    # Construct the final View with the new, cleaner components.
    view = View(

        Item("_"),  # Separator

        main_view_settings,

        Item("_"),  # Separator

        sidebar_settings_grid,

        Item("_"),  # Separator to space this out from further contributions to the pane.

        resizable=True
    )
