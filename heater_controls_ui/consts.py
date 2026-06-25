from heater_controller.consts import DEVICE_NAME

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ").replace("Ui", "UI")
listener_name = f"{PKG}_listener"

# Subscribe to every heater signal (connected/disconnected, heaters_available,
# telemetry). Commands are published outward, so they aren't subscribed here.
ACTOR_TOPIC_DICT = {
    listener_name: [f"{DEVICE_NAME}/signals/#"],
}
