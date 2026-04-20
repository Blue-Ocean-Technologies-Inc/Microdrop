from pathlib import Path

from PySide6.QtGui import QColor
from apptools.preferences.api import PreferencesHelper
from traits.etsconfig.api import ETSConfig
from traits.api import Bool, Str, Directory, Range
from traitsui.api import VGroup, View, Item, Group, RangeEditor, Color
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

    # dialogs:
    suppress_no_shorts_information = Bool(False)

    # ---- Central canvas background styling ----------------------------------
    # `canvas_background_use_custom` is the master switch:
    #   - False → canvas follows the system color scheme (white in light mode,
    #     black in dark mode) as defined in MicrodropCentralCanvas.
    #   - True  → use `canvas_background_color` (picked via a Color dialog in
    #     the preferences view).
    # `canvas_background_opacity` is a percentage (0–100) applied to whichever
    # colour ends up being used, producing the final rgba stylesheet.
    canvas_background_use_custom = Bool(False)
    canvas_background_color = Color()
    canvas_background_opacity = Range(low=0, high=100, value=100)

    def _EXPERIMENTS_DIR_default(self) -> Path:
        default_dir = Path(ETSConfig.user_data) / "Experiments"

        default_dir.mkdir(parents=True, exist_ok=True)

        return default_dir

    def _anytrait_changed(self, trait_name, old, new):
        """Normalize QColor values before letting apptools persist them.

        The `Color` trait delivers a `QColor` object in/out, but apptools'
        PreferencesHelper can only serialize simple scalars to the preferences
        node — a raw QColor raises during storage. We convert it to an integer
        hex string (e.g. `"0xff112233"`) here so the round-trip through
        preferences storage works, and the canvas re-reads it as a QColor via
        the Color trait's own parsing on load.
        """
        if isinstance(new, QColor):
            new = hex(new.rgba())

        super()._anytrait_changed(trait_name, old, new)


microdrop_tab = PreferencesCategory(
    id="microdrop.app.general_settings",
    name="Microdrop General",
)


class MicrodropPreferencesPane(PreferencesPane):
    """Microdrop General preferences pane — hosts app-startup and canvas-
    background groups.
    """

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

    canvas_settings = VGroup(
            Item('canvas_background_use_custom', label="Use Custom Color"),
            Item('canvas_background_color', label="Background Color (hex)",
                 enabled_when='canvas_background_use_custom'),
            Item('canvas_background_opacity', label="Opacity (%)",
                 editor=RangeEditor(low=0, high=100, mode='slider')),
            label="Canvas Background",
            show_border=True,
            style_sheet=preferences_group_style_sheet,
        ),

    view = View(

        Item("_"), # Separator

        app_startup_settings,

        Item("_"),

        canvas_settings,

        Item("_"),  # ensure other contributed pane groups are spaced out from this pane's group.

        resizable=True,
    )


class MicrodropDialogsPreferencesPane(PreferencesPane):
    """Microdrop General preferences pane — 'Dialog Settings' group.

    Contributes to the same `microdrop.app.general_settings` tab as
    MicrodropPreferencesPane but in a separate group so the dialog-related
    toggles can live independently of the canvas/startup controls.
    """

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = MicrodropPreferences

    category = microdrop_tab.id

    ########################################################################################

    view = View(
        Item("_"),  # Separator
        Group(
            Item("suppress_no_shorts_information"),
            label="Dialog Settings",
            show_border=True,
            style_sheet=preferences_group_style_sheet,
        ),
        Item("_"),  # Separator
        resizable=True,
    )

    def apply(self, info=None):
        # super().apply(info)
        pass
