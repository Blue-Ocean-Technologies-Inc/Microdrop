"""Package-level constants for dropbot_protocol_controls.

Hardware request/ack topic constants live in dropbot_controller/consts.py
— this plugin imports them. UI/measurement topics like CALIBRATION_DATA
live in device_viewer/consts.py. See PPT-4 spec section 3, "Topic
ownership rationale" for the layering reasoning.
"""

from device_viewer.consts import CALIBRATION_DATA

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

CALIBRATION_LISTENER_ACTOR_NAME = "calibration_data_listener"

ACTOR_TOPIC_DICT = {
    CALIBRATION_LISTENER_ACTOR_NAME: [CALIBRATION_DATA],
}
