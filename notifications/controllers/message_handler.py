# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dramatiq listener for the notifications plugin: routes its subscribed
topics (consts.ACTOR_TOPIC_DICT) to ``_on_<topic>_triggered`` handlers.

Handlers run on a Dramatiq worker thread. They validate the payload there
and hand the model change to the GUI thread with ``GUI.invoke_later``.
"""

# Third-party imports.
import dramatiq

# Enthought library imports.
from pyface.api import GUI
from traits.api import HasTraits, Instance, Str

# Microdrop package imports.
from user_help_plugin.consts import HelpAvailability, open_tutorial_publisher

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
    unregister_dramatiq_listener_actor,
)

# Local imports.
from ..consts import (
    LISTENER_NAME,
    NotificationMessage,
    NotificationResolveRequest,
    ShowNotificationsPanelRequest,
    parse_help_target,
)
from .notifications_controller import NotificationsController

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NotificationsMessageHandler(HasTraits):
    """Posts NOTIFICATION_POST payloads, shows the pane on request, and
    clears the cards of a resolved condition."""

    #: Acts on the requests.
    controller = Instance(NotificationsController)

    #: Unique Dramatiq listener name; consts.ACTOR_TOPIC_DICT routes to it.
    name = Str(LISTENER_NAME)

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name, class_method=self.listener_actor_routine
        )

    def teardown(self):
        """Release the listener actor, so a re-loaded plugin can register
        the name again."""
        unregister_dramatiq_listener_actor(self.name)
        self.dramatiq_listener_actor = None

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    def _on_post_triggered(self, message):
        notification = NotificationMessage.model_validate_json(message)
        center = self.controller.pane_model.center

        GUI.invoke_later(center.post_message, notification)

    def _on_show_panel_triggered(self, message):
        request = ShowNotificationsPanelRequest.model_validate_json(message)

        GUI.invoke_later(self.controller.show_pane, request.section_id)

    def _on_resolve_triggered(self, message):
        request = NotificationResolveRequest.model_validate_json(message)
        center = self.controller.pane_model.center

        GUI.invoke_later(center.resolve, request.condition_id, request.resolution)

    def _on_availability_triggered(self, message):
        """The help plugin started or stopped: the help links follow."""
        availability = HelpAvailability.model_validate_json(message)
        opener = open_tutorial if availability.available else None

        GUI.invoke_later(setattr, self.controller, "open_help", opener)


def open_tutorial(target):
    """Ask the help plugin to open the tutorial a HelpAction ``target``
    names (``tutorial id#section``)."""
    tutorial_id, anchor = parse_help_target(target)

    open_tutorial_publisher.publish({"tutorial_id": tutorial_id, "anchor": anchor})
