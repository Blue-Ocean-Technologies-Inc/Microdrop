# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from envisage.api import PREFERENCES_CATEGORIES, PREFERENCES_PANES
from traits.api import Any, List

# Microdrop package imports.
from notifications.consts import NOTIFICATION_CATEGORIES
from template_status_and_controls.base_plugin import BaseStatusPlugin
from user_help_plugin.consts import TUTORIAL_ORDER_HARDWARE, TUTORIALS, TutorialEntry

# Local imports.
from .consts import (
    ACTOR_TOPIC_DICT,
    DROPBOT_STATUS_TUTORIAL_HTML_PATH,
    NOTIFICATION_CATEGORY_SPECS,
    PKG,
    PKG_name,
    listener_name,
)


class DropbotStatusAndControlsPlugin(BaseStatusPlugin):
    """Envisage plugin for DropBot status display and controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    #: Help > Tutorials entries for this plugin's pane.
    tutorials = List(contributes_to=TUTORIALS)

    #: The DropBot connecting and disconnecting, as notification kinds.
    notification_categories = List(
        NOTIFICATION_CATEGORY_SPECS, contributes_to=NOTIFICATION_CATEGORIES
    )

    #: The status model, its preferences, the dialog signals and the message
    #: listener, made at start: the listener's routes are registered at
    #: launch, so it must exist before any routed message arrives, not wait
    #: for the pane. The pane builds its view against these.
    status_preferences = Any()
    status_model = Any()
    dialog_signals = Any()
    message_handler = Any()

    def start(self):
        """Make the Qt-free status model and its message listener; the model
        gets its preferences first, as a message handled on a worker thread
        reads them (#1091)."""
        from .message_handler import (
            DialogSignals,
            DropbotStatusAndControlsMessageHandler,
        )
        from .model import DropbotStatusAndControlsModel
        from .preferences import DropbotStatusAndControlsPreferences

        self.status_preferences = DropbotStatusAndControlsPreferences(
            preferences=self.application.preferences_helper.preferences
        )
        self.status_model = DropbotStatusAndControlsModel(
            preferences=self.status_preferences
        )
        self.dialog_signals = DialogSignals()
        self.message_handler = DropbotStatusAndControlsMessageHandler(
            model=self.status_model,
            dialog_signals=self.dialog_signals,
            name=listener_name,
        )

    def stop(self):
        """Release the message listener, so a restart can register it anew."""

        if self.message_handler is not None:
            self.message_handler.teardown()
            self.message_handler = None

    def _get_dock_pane_class(self):
        from .dock_pane import DropbotStatusAndControlsDockPane

        return DropbotStatusAndControlsDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    def _preferences_panes_default(self):
        from .preferences import DropbotStatusAndControlsPreferencesPane

        return [DropbotStatusAndControlsPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import dropbot_status_and_controls_tab

        return [dropbot_status_and_controls_tab]

    def _tutorials_default(self):
        return [
            TutorialEntry(
                title="Dropbot Status & Controls Tutorial",
                path=DROPBOT_STATUS_TUTORIAL_HTML_PATH,
                order=TUTORIAL_ORDER_HARDWARE,
            )
        ]

    # def _get_menu_additions(self) -> list:
    #     from .menus import menu_factory
    #     return [
    #         SchemaAddition(
    #             factory=menu_factory,
    #             before="TaskToggleGroup",
    #             path="MenuBar/View",
    #         )
    #     ]
