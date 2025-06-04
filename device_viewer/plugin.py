# Standard library imports.
import os.path

from traits.api import List
from message_router.consts import ACTOR_TOPIC_ROUTES

# Enthought library imports.
from envisage.api import Plugin
from envisage.ui.tasks.api import TaskFactory

# local imports
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class DeviceViewerPlugin(Plugin):
    """Device Viewer plugin based on enthought envisage's The chaotic attractors plugin."""

    #### 'IPlugin' interface ##################################################

    # The plugin's unique identifier.
    id = PKG

    # The plugin's name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    #### Contributions to extension points made by this plugin ################
    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)
