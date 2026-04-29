"""VideoProtocolControlsPlugin — contributes video/capture/record
columns to the pluggable protocol tree.

Loaded as part of FRONTEND_PLUGINS in examples/plugin_consts.py.
Tasks 3-5 will fill in the columns and add the device_viewer.consts
topic-import dependency; until then this is a pure scaffold.
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import PKG, PKG_name
from .protocol_columns import make_video_column, make_record_column


logger = get_logger(__name__)


class VideoProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [make_video_column(), make_record_column()]
