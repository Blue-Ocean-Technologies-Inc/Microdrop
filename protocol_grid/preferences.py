# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane
from apptools.preferences.api import PreferencesHelper
from traits.api import List, Enum
from traitsui.api import View, Item
from envisage.ui.tasks.api import PreferencesCategory


from microdrop_style.text_styles import preferences_group_style_sheet
from microdrop_utils.preferences_UI_helpers import create_grid_group
from microdrop_utils.pyface_helpers import RangeWithViewHints

from .consts import (
    DEFAULT_CAMERA_PREWARM_SECONDS,
    DEFAULT_REALTIME_SETTLING_SECONDS,
    DEFAULT_LOGS_SETTLING_SECONDS,
)

from logger.logger_service import get_logger
logger = get_logger(__name__)


class ProtocolPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.protocol"

    #### Preferences ##########################################################
    camera_prewarm_seconds = RangeWithViewHints(
        value=DEFAULT_CAMERA_PREWARM_SECONDS,
        low=0.2,
        high=15.0,
        desc="Camera switch on lead time"
    )

    realtime_mode_settling_time_s = RangeWithViewHints(
        value=DEFAULT_REALTIME_SETTLING_SECONDS,
        low=0.5,
        high=15.0,
        desc="Time to allow for realtime mode to settle pre protocol start"
    )

    logs_settling_time_s = RangeWithViewHints(
        value=DEFAULT_LOGS_SETTLING_SECONDS,
        low=0.5,
        high=15.0,
        desc="Time to allow logs post protocol end"
    )

    capture_time = Enum("Step Start", "Step End", value="Step Start")

    def _level_default(self):
        return "INFO"

protocol_grid_tab = PreferencesCategory(
    id="microdrop.protocol.preferences",
    name="Protocol Settings",
    after="microdrop.device_viewer.preferences",
    before="microdrop.peripheral_settings"
)


class ProtocolPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = ProtocolPreferences

    category = protocol_grid_tab.id

    _changed_preferences = List()

    # Create the grid group for the sidebar items.
    camera_settings_grid = create_grid_group(
        ["camera_prewarm_seconds", "capture_time"],
        label_text = ["Camera On Lead Time (s)", "When to Capture Step Picture?"],
        group_label="Camera Config",
        group_show_border=True,
        group_style_sheet=preferences_group_style_sheet,
    )

    general_protocol_settings_grid = create_grid_group(
        items=["realtime_mode_settling_time_s", "logs_settling_time_s"],
        label_text = ["Realtime Mode Pre-Protocol (s)", "Logs Accepted Post-Protocol (s)"],
        group_label="Protocol Settling Times",
        group_show_border=True,
        group_style_sheet=preferences_group_style_sheet,
    )

    view = View(
        Item("_"),  # Separator
        general_protocol_settings_grid,
        Item("_"),
        camera_settings_grid,
        Item("_"),  # Separator to space this out from further contributions to the pane.
        resizable=True
    )
