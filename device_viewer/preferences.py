from apptools.preferences.api import PreferencesHelper
from traits.api import Bool, Dict, Str, Directory, Int
from traits.observation.observe import observe
from traitsui.api import EnumEditor, HGroup, Item, Label, VGroup, View
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_utils.preferences_UI_helpers import create_traitsui_labeled_item_group


class DeviceViewerPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.device_viewer"

    #### Preferences ##########################################################
    DEVICE_VIEWER_SIDEBAR_WIDTH = Int
    ALPHA_VIEW_MIN_HEIGHT = Int
    LAYERS_VIEW_MIN_HEIGHT = Int

device_viewer_tab = PreferencesCategory(
    id="microdrop.device_viewer.startup_preferences",
    name="Device Viewer",
)


class DeviceViewerPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = DeviceViewerPreferences

    category = device_viewer_tab.id

    #### 'AttractorsPreferencesPane' interface ################################

    items = [
        'DEVICE_VIEWER_SIDEBAR_WIDTH',
        'ALPHA_VIEW_MIN_HEIGHT',
        'LAYERS_VIEW_MIN_HEIGHT',
    ]

    groups = [create_traitsui_labeled_item_group(item, show_labels=False) for item in items]

    view = View(
        VGroup(*groups, label="View Settings"),
        resizable=True,
    )