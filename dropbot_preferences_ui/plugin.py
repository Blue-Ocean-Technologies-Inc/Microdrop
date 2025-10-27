from .consts import PKG, PKG_name

from envisage.ids import SERVICE_OFFERS, PREFERENCES_CATEGORIES, PREFERENCES_PANES
from envisage.plugin import Plugin
from traits.api import List

# microdrop imports
from message_router.consts import ACTOR_TOPIC_ROUTES
from logger.logger_service import get_logger
# Initialize logger
logger = get_logger(__name__)


class DropbotPreferencesPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _preferences_panes_default(self):
        from .preferences import DropbotPreferencesPane

        return [DropbotPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import dropbot_tab
        return [dropbot_tab]
