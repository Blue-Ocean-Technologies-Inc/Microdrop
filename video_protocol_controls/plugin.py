# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""VideoProtocolControlsPlugin — contributes video/capture/record
columns to the pluggable protocol tree, plus the listener that keeps the
selected step's capture camera setup and the device viewer's camera in
step (services/camera_settings_sync.py).

Loaded as part of FRONTEND_PLUGINS in examples/plugin_consts.py.
"""

# Enthought library imports.
from envisage.plugin import Plugin
from traits.api import Either, Instance, List

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn

# Local imports.
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
from .protocol_columns import make_capture_column, make_record_column, make_video_column
from .services.camera_settings_sync import CameraSettingsSync

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class VideoProtocolControlsPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    # Mixed contribution: video/record are flat columns, capture is a
    # compound (#396) — same Either the extension point itself declares.
    contributed_protocol_columns = List(
        Either(IColumn, ICompoundColumn),
        contributes_to=PROTOCOL_COLUMNS,
    )

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #: Keeps the selected step's camera setup and the camera in step.
    camera_settings_sync = Instance(CameraSettingsSync)

    def _contributed_protocol_columns_default(self):
        return [make_video_column(), make_record_column(), make_capture_column()]

    def start(self):
        self.camera_settings_sync = CameraSettingsSync()
