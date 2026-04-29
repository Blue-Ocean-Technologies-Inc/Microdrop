"""VideoProtocolControlsPlugin — contributes video/capture/record
columns to the pluggable protocol tree.

Sibling plugin to device_viewer; depends on device_viewer for topic
constants (DEVICE_VIEWER_* topics). Loaded as part of FRONTEND_PLUGINS
in examples/plugin_consts.py (column declarations are a UI concern;
backend handlers stay in device_viewer).
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import PKG, PKG_name


logger = get_logger(__name__)


class VideoProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return []  # filled in by Task 3/4/5
