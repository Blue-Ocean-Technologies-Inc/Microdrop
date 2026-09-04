# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import json
from datetime import UTC, datetime

import dramatiq
import numpy as np
from dropbot import (
    EVENT_CHANNELS_UPDATED,
    EVENT_ENABLE,
    EVENT_SHORTS_DETECTED,
)
from dropbot.proxy import I2cAddressNotSet

from traits.api import Bool, Dict, HasTraits, Instance, Str, observe, provides

from dropbot_controller.consts import DROPBOT_CONNECTED, DROPBOT_DISCONNECTED
from electrode_controller.consts import (
    ELECTRODES_STATE_CHANGE,
    disabled_channels_changed_publisher,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager

from microdrop_utils.dramatiq_controller_base import (
    TimestampedMessage,
    assert_handlers_exist_for_topics,
    generate_class_method_dramatiq_listener_actor,
    invoke_class_method,
)
from microdrop_utils.dramatiq_dropbot_serial_proxy import DramatiqDropbotSerialProxy
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# unit handling
from microdrop_utils.ureg_helpers import ureg

from .consts import (
    ACTOR_TOPIC_DICT,
    CAPACITANCE_UPDATED,
    CHANGE_SETTINGS,
    CHIP_INSERTED,
    DROPBOT_CONNECTION_STATE_KEY,
    HALT,
    HALTED,
    OUTPUT_ENABLE_PIN,
    PKG,
    RETRY_CONNECTION,
    SET_REALTIME_MODE,
    START_DEVICE_MONITORING,
    shorts_detected_publisher,
)
from .interfaces.i_dropbot_controller_base import IDropbotControllerBase
from .preferences import DropbotPreferences

from logger.logger_service import get_logger

logger = get_logger(__name__, level="INFO")
app_globals = get_microdrop_redis_globals_manager()


@provides(IDropbotControllerBase)
class DropbotControllerBase(HasTraits):
    """
    This class provides some methods for handling signals from the proxy.
    But mainly provides a dramatiq listener that captures appropriate
    signals and calls the methods needed.
    """

    proxy = Instance(DramatiqDropbotSerialProxy)
    dropbot_connection_active = Bool(False)
    preferences = Instance(DropbotPreferences)

    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    listener_name = Str(f"{PKG}_listener")

    timestamps = Dict(str, datetime)

    def __del__(self):
        """Cleanup when the controller is destroyed."""
        self.cleanup()

    def cleanup(self):
        """Cleanup resources when the controller is stopped."""
        logger.info("Cleaning up DropbotController resources")
        if self.proxy is not None:
            try:
                self.proxy.terminate()
                logger.info("Dropbot proxy terminated")
            except Exception as e:
                logger.error(f"Error terminating dropbot proxy: {e}")
            finally:
                self.proxy = None
                self.dropbot_connection_active = False

    @observe("dropbot_connection_active")
    def _mirror_connection_state_to_app_globals(self, event):
        """Mirror the connection state to app_globals so any plugin can read
        it synchronously without subscribing to the connected/disconnected
        signals."""
        app_globals[DROPBOT_CONNECTION_STATE_KEY] = event.new
        logger.info(f"App Globals Update: {DROPBOT_CONNECTION_STATE_KEY}: {event.new}")

    def _resolve_handler_name(self, topic: str):
        """Map a subscribed dropbot/hardware topic to its reflective handler
        method name, or None if the topic has no reflective handler (e.g. it
        is handled as a pure side effect, or isn't a dropbot/hardware topic).

        This is the SAME rule listener_actor_routine uses to pick a handler
        at message time, and what the startup handler-existence check (see
        traits_init) verifies against -- kept in one place so the two can't
        drift apart. Whether a resolved '_request' handler is actually
        honoured while disconnected is a runtime gate applied by the
        caller, not a naming concern.
        """
        topics_tree = topic.split("/")
        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1]
        specific_sub_topic = topics_tree[-1]

        if head_topic not in ("dropbot", "hardware"):
            return None

        if topic in (DROPBOT_CONNECTED, DROPBOT_DISCONNECTED):
            return f"on_{specific_sub_topic}_signal"

        # Chip inserted is handled as a pure side effect (see
        # listener_actor_routine), never dispatched reflectively.
        if topic == CHIP_INSERTED:
            return None

        if topic in (START_DEVICE_MONITORING, RETRY_CONNECTION, CHANGE_SETTINGS):
            return f"on_{specific_sub_topic}_request"

        if primary_sub_topic == "requests":
            return f"on_{specific_sub_topic}_request"

        return None

    def listener_actor_routine(
        self, timestamped_message: TimestampedMessage, topic: str
    ):
        """
        A Dramatiq actor that listens to messages.

        Parameters:
        message (str): The received message.
        topic (str): The topic of the message.

        """

        logger.info(
            f"DROPBOT BACKEND LISTENER: Received message: '{timestamped_message}' "
            f"from topic: {topic} at {timestamped_message.timestamp}"
        )

        # find the topics hierarchy: first element is the head topic. Last
        # element is the specific topic
        topics_tree = topic.split("/")
        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1]  # if len(topics_tree) > 1 else ""
        specific_sub_topic = topics_tree[-1]

        # Determine the requested method to call based on the topic, if it is
        # a dropbot request or signal topic for external dropbot signals
        # connected/disconnected, we handle them everytime. For requests,
        # we need to check if we have a dropbot available or not. Unless it
        # is a request to start looking for a device or disconnect the
        # device.

        # 1. Check if it is a dropbot related topic
        if head_topic in ["dropbot", "hardware"]:
            # Handle the connected / disconnected signals
            if topic in [DROPBOT_CONNECTED, DROPBOT_DISCONNECTED]:
                self.dropbot_connection_active = topic == DROPBOT_CONNECTED
                requested_method = self._resolve_handler_name(topic)
            # Chip inserted means device connected. This message can only come
            # from the self.proxy, likely from another thread. Update this
            # thread and return.
            elif topic == CHIP_INSERTED and timestamped_message == "True":
                self.dropbot_connection_active = True
                return

            else:
                requested_method = self._resolve_handler_name(topic)

                # 3. Handle exceptions: specific dropbot requests that would change
                # dropbot connectivity, and dropbot settings change (user preference)
                # run regardless of connection state. All other requests only run
                # if a dropbot is connected.
                is_exception_request = topic in (
                    START_DEVICE_MONITORING,
                    RETRY_CONNECTION,
                    CHANGE_SETTINGS,
                )
                if (
                    requested_method
                    and not is_exception_request
                    and primary_sub_topic == "requests"
                ):
                    if not self.dropbot_connection_active:
                        logger.warning(
                            f"Request for {specific_sub_topic} denied: "
                            f"Dropbot is disconnected."
                        )
                        requested_method = None

        else:
            requested_method = None
            logger.debug(
                f"Ignored request from topic '{topic}': Not a Dropbot-related request."
            )

        if requested_method:
            if (
                self.timestamps.get(topic, datetime.min)
                > timestamped_message.timestamp_dt
            ):
                logger.debug(
                    f"DropbotController: Ignoring older message from topic: "
                    f"{topic} received at {timestamped_message.timestamp_dt}"
                )
                return

            self.timestamps[topic] = timestamped_message.timestamp_dt

            err_msg = invoke_class_method(self, requested_method, timestamped_message)

            if err_msg:
                logger.error(
                    f" {self.listener_name}; Received message: "
                    f"{timestamped_message} from topic: {topic} Failed to "
                    f"execute due to error: {err_msg}"
                )

    ### Initial traits values ######

    def traits_init(self):
        """
        This is equivalent to doing:

        def __init__(self, **traits):
            super().__init__(**traits)

        """

        logger.info("Starting DropbotController listener")

        # Startup check: every non-wildcard topic this instance subscribes to
        # (including composed mixin services, since self is the fully
        # composed controller) must resolve to a real handler method, using
        # the same routing rule listener_actor_routine dispatches with. A
        # typo'd handler name or a stale ACTOR_TOPIC_DICT entry then fails
        # loudly at app start instead of silently dropping messages forever.
        assert_handlers_exist_for_topics(
            self,
            ACTOR_TOPIC_DICT.get(self.listener_name, []),
            handler_name_resolver=self._resolve_handler_name,
        )

        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name, class_method=self.listener_actor_routine
        )

    def _on_dropbot_proxy_connected(self) -> bool:
        """
        Routine to setup dropbot proxy once connection is made

        Returns:
            bool: True if connection was made

        """

        if self.proxy.config.i2c_address != 0:
            self.proxy.initialize_switching_boards()

        else:
            raise I2cAddressNotSet()

        # Configure proxy settings
        try:
            self.proxy.update_state(
                capacitance_update_interval_ms=self.preferences.capacitance_update_interval,
                voltage=self.preferences.last_voltage,
                frequency=self.preferences.last_frequency,
                hv_output_selected=False,
                hv_output_enabled=False,
                event_mask=EVENT_CHANNELS_UPDATED
                | EVENT_SHORTS_DETECTED
                | EVENT_ENABLE,
            )

            # Connect proxy signals
            logger.debug("Connecting DropBot signals to handlers")
            self.proxy.signals.signal("halted").connect(
                self._halted_event_wrapper, weak=False
            )
            self.proxy.signals.signal("output_enabled").connect(
                self._output_state_changed_wrapper, weak=False
            )
            self.proxy.signals.signal("output_disabled").connect(
                self._output_state_changed_wrapper, weak=False
            )
            self.proxy.signals.signal("capacitance-updated").connect(
                self._capacitance_updated_wrapper
            )
            self.proxy.signals.signal("shorts-detected").connect(
                self._shorts_detected_wrapper
            )
            logger.debug("Connected DropBot signals to handlers")

            # Chip may have been inserted before connecting, so `chip-inserted`
            # event may have been missed.
            # Explicitly check if chip is inserted by reading **active low**
            # `OUTPUT_ENABLE_PIN`.
            self.on_chip_check_request("")

            # Configure feedback capacitor
            if self.proxy.config.C16 < 0.3e-6:
                self.proxy.update_state(chip_load_range_margin=-1)

            # reset to last known state
            self.proxy.turn_off_all_channels()

            # Publish disabled channels state so the device viewer syncs with
            # the (now reset) hardware
            self._publish_disabled_channels_from_mask()

            # Manual call because on boot, shorts-detected event may not be
            # triggered.
            self.proxy.detect_shorts()

            logger.info("Enhanced proxy connection setup completed successfully")

            return True

        except Exception as e:
            logger.error(f"Error during enhanced proxy setup: {e}", exc_info=True)
            return False

    ######################################################################
    # Proxy signal handlers
    #######################################################################

    # proxy signal handlers done this way so that these methods can be
    # overrided externally

    @staticmethod
    def _capacitance_updated_wrapper(signal: dict[str, str]):
        utc_timestamp = datetime.now(UTC).timestamp()
        capacitance = float(signal.get("new_value", 0.0)) * ureg.farad
        capacitance_formatted = f"{capacitance.to(ureg.picofarad):.4g~P}"
        voltage = float(signal.get("V_a", 0.0)) * ureg.volt
        voltage_formatted = f"{voltage:.3g~P}"
        dropbot_timestamp = int(signal.get("time_us", 0))
        # create new timestamp

        publish_message(
            topic=CAPACITANCE_UPDATED,
            message=json.dumps(
                {
                    "capacitance": capacitance_formatted,
                    "voltage": voltage_formatted,
                    "instrument_time_us": dropbot_timestamp,
                    "reception_time": utc_timestamp,
                }
            ),
        )

    @staticmethod
    def _shorts_detected_wrapper(signal: dict[str, str]):
        shorts_detected_publisher.publish(shorted_channels=signal.get("values", []))

    @staticmethod
    def _halted_event_wrapper(signal):

        reason = ""
        message = ""

        if signal["error"]["name"] == "output-current-exceeded":
            reason = "because output current was exceeded"

            message = (
                "All channels have been disabled and high voltage has been\n"
                "                            turned off. It is recommended "
                "to restart the DropBot (e.g., unplug all \n"
                "                            cables and plug back in.)."
            )

        elif signal["error"]["name"] == "chip-load-saturated":
            reason = "because chip load feedback exceeded allowable range"
            message = (
                "Requested channels cannot be actuated. Check if you have "
                "too many droplets, or damage on actuated electrodes "
                "before attempting more actuation."
            )

        # send out signal to all interested parties that the dropbot has
        # been halted and request the HALT method
        halted_message = json.dumps(
            {"name": signal["error"]["name"], "reason": reason, "message": message}
        )
        publish_message(topic=HALTED, message=halted_message)

        publish_message(topic=HALT, message=halted_message)

        logger.error(f"DropBot halted due to {reason}")

    @staticmethod
    def _output_state_changed_wrapper(signal: dict[str, str]):
        if signal["event"] == "output_enabled":
            logger.debug("Publishing Chip Inserted")
            publish_message(topic=CHIP_INSERTED, message="True")
        elif signal["event"] == "output_disabled":
            logger.debug("Publishing Chip Not Inserted")
            publish_message(topic=CHIP_INSERTED, message="False")
        else:
            logger.warn(f"Unknown signal received: {signal}")

    ######################## Methods to Expose ###############################

    def on_chip_check_request(self, message):
        """
        Check if chip is inserted by reading **active low** `OUTPUT_ENABLE_PIN`.
        """
        if self.proxy is not None:
            if self.proxy.monitor is not None:
                chip_check_result = not bool(self.proxy.digital_read(OUTPUT_ENABLE_PIN))
                logger.info(f"Chip check result: {chip_check_result}")
                publish_message(topic=CHIP_INSERTED, message=f"{chip_check_result}")

    def on_detect_shorts_request(self, message):
        if self.proxy is not None:
            if self.proxy.monitor is not None:
                shorts_list = self.proxy.detect_shorts()
                logger.info(f"Detected shorts: {shorts_list}")
                # The request came from the user, so always report back — even
                # when there is nothing to report.
                shorts_detected_publisher.publish(
                    shorted_channels=shorts_list, show_window=True
                )

    def on_halt_request(self, message):
        message = json.loads(message)
        name = message.get("name")
        # XXX Refresh channels since channels were disabled.
        self.on_refresh_channels_request()
        # Disable real-time mode.
        publish_message(topic=SET_REALTIME_MODE, message="False")
        logger.error("Halted DropBot: Disconnect everything and reconnect")

        # if chip has too much liquid, continue to allow actuation.
        if name == "chip-load-saturated":
            self.proxy.disabled_channels_mask *= 0

        # Publish the current disabled channels so the device viewer can update
        self._publish_disabled_channels_from_mask()

    def _publish_disabled_channels_from_mask(self):
        """Read the proxy's disabled_channels_mask and publish the indices
        of disabled channels."""
        try:
            mask = np.array(self.proxy.disabled_channels_mask)
            disabled_indices = set(int(i) for i in np.where(mask != 0)[0])
            logger.info(
                f"Publishing disabled channels change: "
                f"{len(disabled_indices)} channels disabled"
            )
            disabled_channels_changed_publisher.publish(disabled_indices)
        except Exception as e:
            logger.error(
                f"Error publishing disabled channels from mask: {e}", exc_info=True
            )

    def on_refresh_channels_request(self):
        # XXX Reassign channel states to trigger a `channels-updated`
        # message since actuated channel states may have changed based
        # on the channels that were disabled.
        self.proxy.turn_off_all_channels()

        publish_message(
            topic=ELECTRODES_STATE_CHANGE,
            message=app_globals.get("last_channels_requested", []),
        )

    def on_reboot_request(self, message):
        logger.critical("Attempting to reboot dropbot microcontroller...")
        self.proxy.reboot()

    ########################################################################################################
