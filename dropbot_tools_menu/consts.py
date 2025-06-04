from dropbot_controller.consts import SELF_TESTS_PROGRESS, ELECTRODES_STATE_CHANGE, DROPBOT_SETUP_SUCCESS, DROPBOT_DISCONNECTED
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from microdrop_application.consts import PKG as microdrop_application_package

# Topics this plugin wants some actors to subscribe to:
ACTOR_TOPIC_DICT = {
    f"{microdrop_application_package}_listener": [ SELF_TESTS_PROGRESS], # This adds the listener to the microdrop application task, not itself
    f"{PKG}_listener": [ 
                                 DROPBOT_SETUP_SUCCESS,
                                 DROPBOT_DISCONNECTED,
                                 SELF_TESTS_PROGRESS
    ]}

