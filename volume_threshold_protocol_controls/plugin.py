"""VolumeThresholdProtocolControlsPlugin — contributes the
volume-threshold per-step column to the pluggable protocol tree.

Pattern mirrors peripheral_protocol_controls /
dropbot_protocol_controls. The column factory lands in Task 6; the
scaffold lands first so plugin-load smoke tests pass.
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import PKG, PKG_name

logger = get_logger(__name__)


class VolumeThresholdProtocolControlsPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        from .protocol_columns.volume_threshold_column import (
            make_volume_threshold_column,
        )
        return [make_volume_threshold_column()]
