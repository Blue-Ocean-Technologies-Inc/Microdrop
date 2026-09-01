# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PortableDropbotProtocolControlsPlugin — contributes the portable
instrument's built-in peripherals (magnet, heater) to the pluggable
protocol tree as compound columns.

The classic rig keeps these in separate plugin repos because they are
separate boards; the portable has them all behind one backend, so the
columns land in this one plugin. Column declarations are a UI concern,
so it loads with PORTABLE_DROPBOT_FRONTEND_PLUGINS; the request
handlers stay in portable_dropbot_controller.
"""

# Enthought library imports.
from envisage.api import Plugin
from traits.api import Instance, List

# Microdrop package imports.
from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn

# Local imports.
from .consts import PKG, PKG_name
from .protocol_columns.magnet_column import make_magnet_column
from .protocol_columns.temperature_column import make_temperature_column

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PortableDropbotProtocolControlsPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    contributed_protocol_columns = List(
        Instance(ICompoundColumn), contributes_to=PROTOCOL_COLUMNS
    )

    def _contributed_protocol_columns_default(self):
        return [make_magnet_column(), make_temperature_column()]
