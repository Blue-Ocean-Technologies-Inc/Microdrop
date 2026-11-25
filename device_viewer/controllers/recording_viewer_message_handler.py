# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dramatiq listener for the Recording Viewer: hands SHOW_RECORDING requests
to the plugin on the GUI thread. Made at the plugin's start, as the request's
route is registered then, before the pane is first shown."""

# Third-party imports.
import dramatiq

# Enthought library imports.
from pyface.api import GUI
from traits.api import Callable, HasTraits, Instance, Str

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
    unregister_dramatiq_listener_actor,
)

# Local imports.
from ..recording_viewer_consts import (
    RECORDING_VIEWER_LISTENER_NAME,
    ShowRecordingRequest,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class RecordingViewerMessageHandler(HasTraits):
    """Routes SHOW_RECORDING to ``show_recording``."""

    #: ``show_recording(path)``, called on the GUI thread: plays the
    #: recording in the Recording Viewer, brought forward.
    show_recording = Callable()

    #: Unique Dramatiq listener name; RECORDING_VIEWER_ACTOR_TOPIC_DICT
    #: routes to it.
    name = Str(RECORDING_VIEWER_LISTENER_NAME)

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

    def _on_show_recording_triggered(self, message):
        request = ShowRecordingRequest.model_validate_json(message)

        GUI.invoke_later(self.show_recording, request.path)
