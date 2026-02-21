import json
from datetime import datetime

import dramatiq
from traits.api import Bool, HasTraits, Instance, Int, List, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    TimestampedMessage,
    generate_class_method_dramatiq_listener_actor,
    invoke_class_method,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from .consts import (
    CHANGE_SETTINGS,
    DROPBOT_CONNECTED,
    DROPBOT_DISCONNECTED,
    DROPBOT_RETRY_CONNECTION,
    DROPBOT_START_DEVICE_MONITORING,
    DROPBOT_REALTIME_MODE_UPDATED,
    OPENDROP_BOARD_INFO,
    OPENDROP_CONNECTED,
    OPENDROP_DISCONNECTED,
    OPENDROP_FEEDBACK_UPDATED,
    OPENDROP_TEMPERATURES_UPDATED,
    PKG,
    REALTIME_MODE_UPDATED,
    RETRY_CONNECTION,
    START_DEVICE_MONITORING,
)
from .interfaces.i_opendrop_controller_base import IOpenDropControllerBase
from .opendrop_serial_proxy import OpenDropSerialProxy
from .preferences import OpenDropPreferences

try:
    import serial
except ImportError:
    serial = None

logger = get_logger(__name__, level="INFO")


@provides(IOpenDropControllerBase)
class OpenDropControllerBase(HasTraits):
    proxy = Instance(OpenDropSerialProxy)
    dropbot_connection_active = Bool(False)
    preferences = Instance(OpenDropPreferences)
    board_id = Int(-1)
    realtime_mode = Bool(False)  # Match frontend default; no electrode push until user enables realtime
    feedback_enabled = Bool(False)
    set_temperatures = List(Int, value=[25, 25, 25], minlen=3, maxlen=3)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str(f"{PKG}_listener")
    timestamps = Instance(dict, args=())

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if self.proxy is not None:
            try:
                self.proxy.close()
            except Exception as exc:
                logger.warning(f"Error closing OpenDrop proxy during cleanup: {exc}")
        self.proxy = None
        self.dropbot_connection_active = False

    def listener_actor_routine(self, timestamped_message: TimestampedMessage, topic: str):
        topics_tree = topic.split("/")
        if len(topics_tree) < 3:
            return

        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1]
        specific_sub_topic = topics_tree[-1]
        requested_method = None

        if head_topic not in {"opendrop", "dropbot"}:
            return

        if topic in {OPENDROP_CONNECTED, DROPBOT_CONNECTED}:
            self.dropbot_connection_active = True
            requested_method = f"on_{specific_sub_topic}_signal"
        elif topic in {OPENDROP_DISCONNECTED, DROPBOT_DISCONNECTED}:
            self.dropbot_connection_active = False
            requested_method = f"on_{specific_sub_topic}_signal"
        elif topic in {
            START_DEVICE_MONITORING,
            RETRY_CONNECTION,
            CHANGE_SETTINGS,
            DROPBOT_START_DEVICE_MONITORING,
            DROPBOT_RETRY_CONNECTION,
        }:
            requested_method = f"on_{specific_sub_topic}_request"
        elif primary_sub_topic == "requests":
            if self.dropbot_connection_active:
                requested_method = f"on_{specific_sub_topic}_request"
            else:
                logger.warning(
                    f"Request for '{specific_sub_topic}' denied: OpenDrop is disconnected."
                )

        if requested_method:
            if self.timestamps.get(topic, datetime.min) > timestamped_message.timestamp_dt:
                return
            self.timestamps[topic] = timestamped_message.timestamp_dt
            err_msg = invoke_class_method(self, requested_method, timestamped_message)
            if err_msg:
                logger.error(f"Error handling topic {topic}: {err_msg}")

    def traits_init(self):
        logger.info("Starting OpenDropController listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )
        self.feedback_enabled = bool(self.preferences.feedback_enabled) if self.preferences else False
        if self.preferences:
            self.set_temperatures = [
                int(self.preferences.temperature_1),
                int(self.preferences.temperature_2),
                int(self.preferences.temperature_3),
            ]

    def _publish_connected(self):
        publish_message(topic=OPENDROP_CONNECTED, message="True")
        publish_message(topic=DROPBOT_CONNECTED, message="True")

    def _publish_disconnected(self):
        publish_message(topic=OPENDROP_DISCONNECTED, message="True")
        publish_message(topic=DROPBOT_DISCONNECTED, message="True")

    def _publish_realtime_mode(self):
        value = "True" if self.realtime_mode else "False"
        publish_message(topic=REALTIME_MODE_UPDATED, message=value)
        publish_message(topic=DROPBOT_REALTIME_MODE_UPDATED, message=value)

    def _publish_telemetry(self, telemetry: dict):
        temperatures = {
            "t1": telemetry.get("temperature_1"),
            "t2": telemetry.get("temperature_2"),
            "t3": telemetry.get("temperature_3"),
        }
        publish_message(topic=OPENDROP_TEMPERATURES_UPDATED, message=json.dumps(temperatures))

        feedback_active = int(telemetry.get("feedback_mask", []).sum()) if telemetry.get("feedback_mask") is not None else 0
        publish_message(
            topic=OPENDROP_FEEDBACK_UPDATED,
            message=json.dumps({"active_channels": feedback_active}),
        )

        board_id = telemetry.get("board_id")
        if board_id is not None:
            self.board_id = int(board_id)
            publish_message(
                topic=OPENDROP_BOARD_INFO,
                message=json.dumps({"board_id": self.board_id}),
            )

    def _push_state_to_device(self, force: bool = False):
        if self.proxy is None:
            return None
        if (not force) and (not self.realtime_mode):
            return None

        try:
            telemetry = self.proxy.write_state(
                feedback_enabled=self.feedback_enabled,
                temperatures_c=self.set_temperatures,
                read_timeout_ms=int(self.preferences.read_timeout_ms),
            )
        except OSError as e:
            logger.warning(
                "OpenDrop device disconnected (OSError errno=%s).",
                getattr(e, "errno", e),
            )
            self.on_disconnected_signal("")
            return None
        except Exception as e:
            if serial is not None and isinstance(e, serial.SerialException):
                logger.warning(
                    "OpenDrop device disconnected (SerialException: %s).", e
                )
                self.on_disconnected_signal("")
                return None
            raise

        if not telemetry.get("connected", False):
            logger.warning("OpenDrop response timeout/disconnect detected.")
            self._publish_disconnected()
            self.on_disconnected_signal("")
            return None

        self._publish_telemetry(telemetry)
        return telemetry

    def on_connected_signal(self, message):
        if not self.dropbot_connection_active:
            self.dropbot_connection_active = True

    def on_disconnected_signal(self, message):
        self.dropbot_connection_active = False
        if self.proxy is not None:
            try:
                self.proxy.close()
            except Exception:
                pass
            self.proxy = None
