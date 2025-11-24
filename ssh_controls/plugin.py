from traits.api import List, Str
from envisage.api import Plugin

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from logger.logger_service import get_logger
logger = get_logger(__name__)

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class SSHControlsPlugin(Plugin):
    """ Contributes UI actions on top of the IPython Kernel Plugin. """

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"{PKG_name} Plugin"

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Contributions to extension points made by this plugin ################

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def start(self):
        """ Initialize the dropbot on plugin start """

        from .service import SSHService

        logger.debug("Starting SSH Controls Listener")
        self.ssh_controller = SSHService()
