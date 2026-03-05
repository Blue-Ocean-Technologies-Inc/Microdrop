# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# mr box hardware id
MR_BOX_HWID = 'VID:PID=0403:6015'

DEVICE_NAME = "ZStage"

# Topics published by this plugin
CONNECTED = f'{DEVICE_NAME}/signals/connected'
DISCONNECTED = f'{DEVICE_NAME}/signals/disconnected'
ZSTAGE_POSITION_UPDATED = f'{DEVICE_NAME}/signals/position_updated'

# Service Request Topics
START_DEVICE_MONITORING = f"{DEVICE_NAME}/requests/start_device_monitoring"
GO_HOME = f"{DEVICE_NAME}/requests/go_home"
MOVE_UP = f"{DEVICE_NAME}/requests/move_up"
MOVE_DOWN = f"{DEVICE_NAME}/requests/move_down"
SET_POSITION = f"{DEVICE_NAME}/requests/set_position"
RETRY_CONNECTION = f"{DEVICE_NAME}/requests/retry_connection"
UPDATE_CONFIG = f"{DEVICE_NAME}/requests/update_config"

# Error Topics
ERROR = f'{DEVICE_NAME}/error'

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        f"{DEVICE_NAME}/requests/#",
        CONNECTED,
        DISCONNECTED,
    ]}

DEFAULT_DOWN_HEIGHT_MM, DEFAULT_UP_HEIGHT_MM,  = 0.5, 18
MIN_ZSTAGE_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM = 0.5, 25.0