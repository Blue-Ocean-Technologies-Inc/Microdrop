from dropbot_controller.consts import SELF_TESTS_PROGRESS, DROPBOT_SETUP_SUCCESS
from microdrop_utils.dramatiq_dropbot_serial_proxy import DISCONNECTED
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from device_viewer.consts import PKG as device_viewer_package

# Topics this plugin wants some actors to subscribe to:
ACTOR_TOPIC_DICT = {
    f"{device_viewer_package}_listener": [SELF_TESTS_PROGRESS],
    f"{PKG}_listener": [ 
                                 DROPBOT_SETUP_SUCCESS,
                                 DISCONNECTED
    ]}


# Topics emitted by this plugin
ELECTRODES_STATE_CHANGE = 'dropbot/requests/electrodes_state_change'
