import platform

from envisage.ui.tasks.api import PreferencesPane
from traitsui.api import View, VGroup, HGroup, Label, Item, Group
from apptools.preferences.api import PreferencesHelper
from traits.api import Str, Bool

from device_viewer.preferences import device_viewer_tab
from microdrop_style.text_styles import preferences_group_style_sheet
from microdrop_utils.preferences_UI_helpers import create_item_label_group

os_name = platform.system()

if os_name == "Windows":
    default_video_format = "NV12"
    strict_video_format = False

elif os_name == "Linux":
    default_video_format = "Jpeg"
    strict_video_format = True

elif os_name == "Darwin":
    default_video_format = "NV12"
    strict_video_format = False

else:
    strict_video_format = False
    default_video_format = "Jpeg"


class CameraPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "camera"

    #### Preferences ##########################################################
    video_format = Str
    strict_video_format = Bool

    def _video_format_default(self):
        return default_video_format

    def _strict_video_format_default(self):
        return strict_video_format


class CameraPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = CameraPreferences

    category = device_viewer_tab.id

    ########################################################################################
    video_format_item = create_item_label_group("video_format", label_text="Video Format")
    strict_video_format_item = create_item_label_group("strict_video_format",
                                                       label_text="Strictly Use Only Preferred Video Format?")

    view = View(
        Item("_"),  # Separator
        Group(
            [video_format_item, strict_video_format_item],
            label="Video Format",
            show_labels=False,
            show_border=True,
            style_sheet=preferences_group_style_sheet,
        ),
        Item("_"),  # Separator
    )
