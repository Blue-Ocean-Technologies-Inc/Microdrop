"""HeaterProtocolControlsPlugin — contributes the heater temperature compound
column to the pluggable protocol tree.

Sibling plugin to heater_controller (which owns the topic constants and the
request handler / proxy watch). A frontend/UI concern, loaded with the other
protocol-controls plugins.
"""
from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn

from .consts import PKG, PKG_name
from .protocol_columns.temperature_column import make_temperature_column

logger = get_logger(__name__)


class HeaterProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(ICompoundColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [make_temperature_column()]
