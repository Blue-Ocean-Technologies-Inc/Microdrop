# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Per-run device context for the protocol logger, assembled by the dock
pane from app_globals (keeps the logger units decoupled from the device
viewer + application — no reaching into their panes/models)."""

from pathlib import Path

from traits.api import Any, Dict, Float, HasTraits, Instance, Int

from device_viewer.consts import CHANNEL_AREAS_KEY, DEVICE_SVG_PATH_KEY
from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


class LoggingDeviceContext(HasTraits):
    experiment_directory = Instance(Path)
    # Full path to the device SVG (from app_globals[DEVICE_SVG_PATH_KEY]); the
    # report heatmap loads it. None -> no heatmap. Any: tolerates Path or str.
    device_svg_path = Any
    # channel -> electrode area (mm^2); from app_globals[CHANNEL_AREAS_KEY].
    channel_areas = Dict(Int, Float)
    # dropbot calibration snapshot; live updates flow through the controller.
    # None -> force is None (legacy parity). Any: tolerates float or None.
    capacitance_per_unit_area = Any

    def _channel_areas_default(self):
        return {int(k): float(v) for k, v in (app_globals.get(CHANNEL_AREAS_KEY) or {}).items()}

    def _device_svg_path_default(self):
        return app_globals.get(DEVICE_SVG_PATH_KEY)
