from pathlib import Path

from apptools.preferences.api import PreferencesHelper
from traits.etsconfig.api import ETSConfig
from traits.api import Bool, Str, Directory
from traitsui.api import VGroup, View, Item
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_style.text_styles import preferences_group_style_sheet

from microdrop_utils.preferences_UI_helpers import create_item_label_group


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

    EXPERIMENTS_DIR = Directory()

    def _EXPERIMENTS_DIR_default(self) -> Path:
        default_dir = Path(ETSConfig.user_data) / "Experiments"

        default_dir.mkdir(parents=True, exist_ok=True)

        return default_dir


microdrop_tab = PreferencesCategory(
    id="microdrop.app.general_settings",
    name="Microdrop General",
)


class MicrodropPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = MicrodropPreferences

    category = microdrop_tab.id

    #### 'MicrodropPreferencesPane' interface ################################

    app_startup_settings = VGroup(
            create_item_label_group('always_use_default_layout'),
            label="Application Startup",
            show_border=True,
            style_sheet=preferences_group_style_sheet,
        ),

    view = View(

        Item("_"), # Separator

        app_startup_settings,

        Item("_"),  # ensure other contributed pane groups are spaced out from this pane's group.

        resizable=True,
    )