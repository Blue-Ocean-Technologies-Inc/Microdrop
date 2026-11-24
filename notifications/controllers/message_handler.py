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

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
    unregister_dramatiq_listener_actor,
)

# Local imports.
from ..consts import LISTENER_NAME, NotificationMessage, ShowNotificationsPanelRequest
from .notifications_controller import NotificationsController

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NotificationsMessageHandler(HasTraits):
    """Posts NOTIFICATION_POST payloads and shows the pane on request."""

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
