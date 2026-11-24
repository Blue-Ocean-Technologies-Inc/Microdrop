# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The real NotificationsPlugin with the prototype's views swapped in.

Same id, topics, log forwarding and load-failure notices as the product
plugin; the model, controller, bell and drawer are the prototype's, and the
toasts are new. Needs attention and the notification list are sections of
their own, after the contributed ones.
"""

# Standard library imports.
import logging

# Enthought library imports.
from pyface.api import GUI
from traits.api import Any, Instance, List

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from notifications.consts import ACTOR_TOPIC_DICT, LISTENER_NAME
from notifications.controllers.load_failure_notifier import PluginLoadFailureNotifier
from notifications.controllers.message_handler import NotificationsMessageHandler
from notifications.plugin import NotificationsPlugin
from notifications.services.log_forwarder import NotificationLogHandler

# Local imports.
from .ux_consts import (
    NOTIFICATION_RESOLVE,
    NotificationResolveRequest,
    UxNotificationMessage,
)
from .ux_controllers import ToastStackController, UxNotificationsController
from .ux_models import AttentionSection, HistorySection

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class UxMessageHandler(NotificationsMessageHandler):
    """Reads NOTIFICATION_POST payloads with the prototype's additions."""

    def _on_post_triggered(self, message):
        notification = UxNotificationMessage.model_validate_json(message)
        center = self.controller.pane_model.center

        GUI.invoke_later(center.post_message, notification)

    def _on_resolve_triggered(self, message):
        request = NotificationResolveRequest.model_validate_json(message)
        center = self.controller.pane_model.center

        GUI.invoke_later(center.resolve, request.condition_id, request.resolution)


class UxNotificationsPlugin(NotificationsPlugin):
    """NotificationsPlugin with toasts and the prototype's drawer and bell."""

    controller = Instance(UxNotificationsController)

    #: The product's routes, plus conditions clearing.
    actor_topic_routing = List(
        [{LISTENER_NAME: [*ACTOR_TOPIC_DICT[LISTENER_NAME], NOTIFICATION_RESOLVE]}],
        contributes_to=ACTOR_TOPIC_ROUTES,
    )

    #: Pops new notifications up and times them.
    toast_controller = Instance(ToastStackController)

    #: Shows the toasts on the main window.
    _toast_view = Any()

    #: The prototype's own sections: Needs attention and the list.
    _own_sections = Any()

    def start(self):
        """As the product plugin, with the prototype's classes."""
        from .bell_view import UxBellIndicator
        from .drawer_view import UxDrawerHost
        from .toast_view import ToastStackView

        self.connect_extension_point_traits()

        self.controller = UxNotificationsController()
        pane_model = self.controller.pane_model
        center = pane_model.center
        self._own_sections = [
            AttentionSection(pane_model=pane_model),
            HistorySection(pane_model=pane_model),
        ]
        self._show_sections()

        self._log_handler = NotificationLogHandler(center)
        logging.getLogger().addHandler(self._log_handler)

        self._message_handler = UxMessageHandler(controller=self.controller)
        self._load_failure_notifier = PluginLoadFailureNotifier(
            center=center,
            status=getattr(self.application, "plugin_load_status", None),
        )

        self._bell = UxBellIndicator(pane_model=pane_model)
        self._bell.widget.clicked.connect(self.controller.toggle_pane)
        self.status_bar_icons.append(self._bell.widget)

        self.toast_controller = ToastStackController(pane_model=pane_model)
        self._toast_view = ToastStackView(
            pane_model=pane_model,
            controller=self.toast_controller,
            bell=self._bell.widget,
        )
        self._drawer_host = UxDrawerHost(
            model=pane_model, click_outside_exempt=[self._bell.widget]
        )

        window = getattr(self.application, "active_window", None)

        if window is not None and window.control is not None:
            self._attach_drawer(window)

    def _attach_drawer(self, window):
        """Put the drawer and the toasts on ``window``; toasts start now."""
        super()._attach_drawer(window)

        self._toast_view.attach(window.control)
        self.toast_controller.enabled = True

    def _show_sections(self):

        if self.controller is not None:
            own = self._own_sections or []
            self.controller.pane_model.sections = [*self.sections, *own]
