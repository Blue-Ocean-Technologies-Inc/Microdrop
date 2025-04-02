from dropbot_controller.consts import SELF_TESTS_PROGRESS

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from device_viewer.consts import PKG as device_viewer_package

# Topics this plugin wants some actors to subscribe to:
ACTOR_TOPIC_DICT = {
    f"{device_viewer_package}_listener": [
                                 SELF_TESTS_PROGRESS,
    ]}


# Topics emitted by this plugin
ELECTRODES_STATE_CHANGE = 'dropbot/requests/electrodes_state_change'
