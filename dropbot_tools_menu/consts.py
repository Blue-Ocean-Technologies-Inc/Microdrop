from dropbot_controller.consts import SELF_TESTS_PROGRESS, ELECTRODES_STATE_CHANGE

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from microdrop_application.consts import PKG as microdrop_application_package

# Topics this plugin wants some actors to subscribe to:
ACTOR_TOPIC_DICT = {
    f"{microdrop_application_package}_listener": [ # This adds the listener to the microdrop application task, not itself
                                 SELF_TESTS_PROGRESS,
    ]}

