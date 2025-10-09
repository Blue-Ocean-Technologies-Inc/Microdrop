from apptools.preferences.api import PreferencesHelper
from traits.api import Bool, Dict, Str, Directory
from traitsui.api import EnumEditor, HGroup, Item, Label, VGroup, View
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_utils.preferences_UI_helpers import create_traitsui_labeled_item_group


class MicrodropPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.app"

    #### Preferences ##########################################################

    # The task to activate on app startup if not restoring an old layout.
    default_task = Str

    # Whether to always apply the default application-level layout.
    # See TasksApplication for more information.
    always_use_default_layout = Bool


microdrop_tab = PreferencesCategory(
    id="microdrop.app.startup_preferences",
    name="Application Startup",
)


class MicrodropPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = MicrodropPreferences

    category = microdrop_tab.id

    #### 'AttractorsPreferencesPane' interface ################################

    view = View(
        VGroup(
            create_traitsui_labeled_item_group('always_use_default_layout', show_labels=False),
            label="Application Startup",
        ),
        resizable=True,
    )