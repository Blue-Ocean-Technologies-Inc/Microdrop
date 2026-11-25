# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Recording Viewer's pane and its SHOW_RECORDING request: its own module,
as ``device_viewer.consts`` is past its length baseline. A sibling plugin
needing them gets them re-exported from ``device_viewer.consts``."""

# Third-party imports.
from pydantic import BaseModel, ConfigDict, Field

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# The device viewer's package, as device_viewer.consts names it.
PKG = ".".join(__name__.split(".")[:-1])

#: The Recording Viewer dock pane.
RECORDING_VIEWER_DOCK_PANE_ID = f"{PKG}.video_viewer.dock_pane"

#: Request: play the recording at ``path`` in the Recording Viewer, its pane
#: raised where it is, or popped out when closed (ShowRecordingRequest). The
#: camera's video cards send it from their Show button.
SHOW_RECORDING = "ui/device_viewer/recording_viewer/show_recording"


class ShowRecordingRequest(BaseModel):
    """The SHOW_RECORDING payload."""

    #: Built on first use, not at launch.
    model_config = ConfigDict(defer_build=True)

    #: The recording file to play.
    path: str = Field(min_length=1)


show_recording_publisher = ValidatedTopicPublisher(
    topic=SHOW_RECORDING, validator_class=ShowRecordingRequest
)

#: The Recording Viewer's listener, made at the plugin's start so a request
#: is heard before the pane is first shown.
RECORDING_VIEWER_LISTENER_NAME = f"{PKG}_recording_viewer_listener"
RECORDING_VIEWER_ACTOR_TOPIC_DICT = {RECORDING_VIEWER_LISTENER_NAME: [SHOW_RECORDING]}
