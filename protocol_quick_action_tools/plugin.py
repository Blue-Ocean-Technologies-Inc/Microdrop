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
        from .quick_actions.add_group import make_add_group_action
        from .quick_actions.add_step import make_add_step_action
        from .quick_actions.browse_reports import make_browse_reports_action
        from .quick_actions.delete_row import make_delete_row_action
        from .quick_actions.import_protocol import make_import_protocol_action
        from .quick_actions.new_protocol import make_new_protocol_action
        from .quick_actions.open_protocol import make_open_protocol_action
        from .quick_actions.save_protocol import make_save_protocol_action
        return [
            make_add_step_action(),
            make_delete_row_action(),
            make_add_group_action(),
            make_import_protocol_action(),
            make_open_protocol_action(),
            make_save_protocol_action(),
            make_new_protocol_action(),
            make_browse_reports_action(),
        ]
