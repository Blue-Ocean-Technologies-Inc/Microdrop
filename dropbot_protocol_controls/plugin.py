"""DropbotProtocolControlsPlugin — contributes voltage/frequency
columns to the pluggable protocol tree.
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import PKG, PKG_name
from .protocol_columns.voltage_column import make_voltage_column
from .protocol_columns.frequency_column import make_frequency_column


logger = get_logger(__name__)


class DropbotProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [make_voltage_column(), make_frequency_column()]
