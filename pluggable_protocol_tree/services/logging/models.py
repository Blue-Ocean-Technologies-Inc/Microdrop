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

# Standard library imports.
import math
from pathlib import Path

# Enthought library imports.
from traits.api import Any, Dict, Float, HasTraits, Instance, Int, Str

# Microdrop package imports.
from device_viewer.consts import (
    CHANNEL_AREAS_KEY,
    DEVICE_SVG_PATH_KEY,
    FILLER_CAPACITANCE_KEY,
)
from dropbot_status_and_controls.consts import (
    DIELECTRIC_MATERIAL_KEY,
    DIELECTRIC_MATERIALS,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
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

    #: Filler (air or oil) calibration in pF/mm^2, from
    #: app_globals[FILLER_CAPACITANCE_KEY]; subtracted from C/A for the
    #: thickness column. None when the device viewer has not measured one.
    filler_capacitance_per_unit_area = Any

    #: Dielectric picked in the DropBot status pane, from
    #: app_globals[DIELECTRIC_MATERIAL_KEY]. Empty when never published.
    dielectric_material = Str

    #: Relative permittivity of ``dielectric_material`` (float), or None when
    #: the material is unset or the "Pick a dielectric..." placeholder.
    dielectric_constant = Any

    def _channel_areas_default(self):
        return {
            int(k): float(v)
            for k, v in (app_globals.get(CHANNEL_AREAS_KEY) or {}).items()
        }

    def _device_svg_path_default(self):
        return app_globals.get(DEVICE_SVG_PATH_KEY)

    def _dielectric_material_default(self):
        # Optional report data: an unreachable Redis (tests, headless) must
        # not stop the run from logging, so it reads as "not set".
        try:
            return app_globals.get(DIELECTRIC_MATERIAL_KEY) or ""
        except Exception as e:
            logger.debug(f"could not read the dielectric material: {e}")
            return ""

    def _filler_capacitance_per_unit_area_default(self):
        # Optional report data, tolerant of an unreachable Redis like the
        # dielectric material above.
        try:
            filler = app_globals.get(FILLER_CAPACITANCE_KEY)
        except Exception as e:
            logger.debug(f"could not read the filler calibration: {e}")
            return None

        return None if filler is None else float(filler)

    def _dielectric_constant_default(self):
        epsilon_r = DIELECTRIC_MATERIALS.get(self.dielectric_material)

        if epsilon_r is None or math.isnan(epsilon_r):
            return None

        return epsilon_r
