# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dramatiq listener for the image viewer: routes its subscribed topics
(consts.ACTOR_TOPIC_DICT) to ``_on_<topic>_triggered`` handlers.

Handlers run on the Dramatiq worker thread; every model write is handed
to the GUI thread with ``GUI.invoke_later``, so the observers it fires
(views, controllers) run where Qt expects them (#754)."""

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
from .analysis.roi_model import RoiAnalysisModel
from .consts import LISTENER_NAME

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ImageViewerMessageHandler(HasTraits):
    """Keeps the analysis model's ``protocol_running`` in step with the
    protocol tree's PROTOCOL_RUNNING messages."""

    #: The model the handlers write to.
    model = Instance(RoiAnalysisModel)

    #: Unique Dramatiq listener name; consts.ACTOR_TOPIC_DICT routes to it.
    name = Str(LISTENER_NAME)

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def traits_init(self):
        logger.info(f"Starting message listener: {self.name!r}")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name, class_method=self.listener_actor_routine
        )

    def teardown(self):
        """Release the listener actor, so a re-loaded plugin can register
        the name again."""
        logger.info(f"Stopping message listener: {self.name!r}")
        unregister_dramatiq_listener_actor(self.name)
        self.dramatiq_listener_actor = None

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    def _on_protocol_running_triggered(self, message):
        running = message.casefold() == "true"
        GUI.invoke_later(setattr, self.model, "protocol_running", running)
