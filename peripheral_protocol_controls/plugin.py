"""PeripheralProtocolControlsPlugin — contributes the magnet
compound column to the pluggable protocol tree.

Sibling plugin to peripheral_controller; depends on peripheral_controller
for topic constants and request-handler dispatch. Loaded as part of
FRONTEND_PLUGINS in examples/plugin_consts.py (column declarations are
a UI concern; backend RPC handlers stay in peripheral_controller).
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_compound_column import (
    ICompoundColumn,
)

from .consts import PKG, PKG_name
from .protocol_columns.magnet_column import make_magnet_column


logger = get_logger(__name__)


class PeripheralProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(ICompoundColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [make_magnet_column()]
