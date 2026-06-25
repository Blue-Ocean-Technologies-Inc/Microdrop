"""Heater controller backend demo.

Starts the heater backend, kicks off connection monitoring, and lets the
serial reader thread print everything the heater sends (plain-text lines and
§<FRAME>{json} telemetry). A few seconds after start it sends a ``whoami``
command to demonstrate the request -> serial write path.

Run (heater plugged in over USB):
    python examples/demos/run_heater_controller_demo.py

Requires Redis (started here via redis_server_context) and a heater on
VID:PID=2E8A:0005. Without the heater, the monitor just keeps polling.
"""
# sys imports
import os
import sys
import time
import threading

# enthought imports
from envisage.api import CorePlugin
from envisage.application import Application

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# plugin imports
from heater_controller.plugin import HeaterControllerPlugin
from heater_controller.consts import START_DEVICE_MONITORING, SEND_COMMAND
from message_router.plugin import MessageRouterPlugin

# local helpers imports
from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

logger = get_logger(__name__)

DEMO_COMMAND_DELAY_S = 8.0


def _demo_traffic():
    """Kick off monitoring, then send a sample command once the heater has had a
    chance to connect."""
    logger.info("Demo: requesting heater connection monitoring")
    publish_message(message="", topic=START_DEVICE_MONITORING)

    time.sleep(DEMO_COMMAND_DELAY_S)
    logger.info("Demo: sending 'whoami' to the heater")
    publish_message(message="whoami", topic=SEND_COMMAND)


def main(args):
    """Run the heater backend demo."""
    plugins = [CorePlugin(), MessageRouterPlugin(), HeaterControllerPlugin()]
    app = Application(plugins=plugins)

    with redis_server_context(), dramatiq_workers_context():
        app.start()

        # Drive monitoring + a sample command off the main thread.
        threading.Thread(target=_demo_traffic, daemon=True).start()

        logger.info("Heater demo running. Watch the logs for HEATER RX / TELEMETRY. Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Heater demo stopping")
        finally:
            app.stop()


if __name__ == "__main__":
    main(sys.argv)
