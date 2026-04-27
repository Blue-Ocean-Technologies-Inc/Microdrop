"""DropbotProtocolControlsPlugin — contributes voltage/frequency
columns to the pluggable protocol tree.

Sibling plugin to dropbot_controller; depends on dropbot_controller
for topic constants and request-handler dispatch. Loaded as part of
DROPBOT_BACKEND_PLUGINS in examples/plugin_consts.py.
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from .consts import PKG, PKG_name


logger = get_logger(__name__)


class DropbotProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # contributed_protocol_columns is added in task 11.
