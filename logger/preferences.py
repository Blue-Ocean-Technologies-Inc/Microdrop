from apptools.preferences.api import PreferencesHelper

from traits.api import Enum, observe
from traitsui.api import VGroup, View, Item, FileEditor, EnumEditor, Group, Handler

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from logger.consts import CHANGE_LOG_LEVEL
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.preferences_UI_helpers import create_grid_group, create_item_label_group
from microdrop_application.preferences import microdrop_tab

import logging
from logger.logger_service import get_logger, LEVELS

logger = get_logger(__name__)

from microdrop_style.text_styles import preferences_group_style_sheet

class LoggerPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.logger"

    #### Preferences ##########################################################
    # The log levels
    level = Enum("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class LoggerPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = LoggerPreferences

    category = microdrop_tab.id

    #### Preferences ##########################################################

    logger_view = Item(
        name="level",
        editor=EnumEditor(
            values={
                "DEBUG": "1:Debug",
                "INFO": "2:Info",
                "WARNING": "3:Warning",
                "ERROR": "4:Error",
                "CRITICAL": "5:Critical",
            },
        ),
        style="simple",
    ),

    # The view used to change the plugin preferences
    traits_view = View(
            Group(
                logger_view,
                label="Logger Settings",
                show_border=True,
                style_sheet=preferences_group_style_sheet,
            ),
        )

    def apply(self, info=None):
        super().apply(info)
        ROOT_LOGGER = logging.getLogger()

        # check if pane log level different from model and publish event accoridngly.
        if LEVELS[self.model.level.upper()] != ROOT_LOGGER.getEffectiveLevel():
            logger.info(f"Log level change. Publish log level: {self.model.level}")
            ROOT_LOGGER.setLevel(LEVELS[self.model.level])
            publish_message(self.model.level, CHANGE_LOG_LEVEL)
