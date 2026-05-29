"""ProtocolQuickActionToolsPlugin — contributes the 8 legacy quick
actions to the pluggable protocol tree.

Pattern mirrors peripheral_protocol_controls / dropbot_protocol_controls.
The factories ship in task 12; the scaffold lands first so the rest of
the plan can land in any order without "import broken" stages."""

from envisage.plugin import Plugin
from traits.api import List

from pluggable_protocol_tree.consts import PROTOCOL_QUICK_ACTIONS

from logger.logger_service import get_logger

from .consts import PKG, PKG_name

logger = get_logger(__name__)


class ProtocolQuickActionToolsPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    contributed_quick_actions = List(contributes_to=PROTOCOL_QUICK_ACTIONS)

    def _contributed_quick_actions_default(self):
        # Filled in by task 12.
        return []
