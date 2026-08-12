import json
from datetime import datetime

import dramatiq
from traits.api import Any, Bool, HasTraits, Instance, Int, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    TimestampedMessage,
    generate_class_method_dramatiq_listener_actor,
    invoke_class_method,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from .consts import (
    ALARM_RAISED,
    ERROR_RAISED,
    MOTOR_IDS,
    MOTORS_UPDATED,
    PKG,
    PORTABLE_DROPBOT_CONNECTED,
    PORTABLE_DROPBOT_DISCONNECTED,
    REALTIME_MODE_UPDATED,
    RETRY_CONNECTION,
    STATUS_UPDATED,
)
from .interfaces.i_portable_dropbot_controller_base import (
    IPortableDropbotControllerBase,
)
from .preferences import PortableDropbotPreferences

logger = get_logger(__name__, level="INFO")


@provides(IPortableDropbotControllerBase)
class PortableDropbotControllerBase(HasTraits):
    #: The driver's DropletBotSession; Any because portable_dropbot is
    #: an optional dependency (the monitor mixin imports it lazily).
    proxy = Any()
    portable_dropbot_connection_active = Bool(False)
    preferences = Instance(PortableDropbotPreferences)
    realtime_mode = Bool(False)
    voltage = Int()
    frequency = Int()
    light_intensity = Int()

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str(f"{PKG}_listener")
    timestamps = Instance(dict, args=())

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if self.proxy is not None:
            try:
                self.proxy.disconnect()
            except Exception as exc:
                logger.warning(f"Error disconnecting Portable Dropbot "
                               f"during cleanup: {exc}")
        self.proxy = None
        self.portable_dropbot_connection_active = False

    def listener_actor_routine(self, timestamped_message: TimestampedMessage,
                               topic: str):
        topics_tree = topic.split("/")
        if len(topics_tree) < 3:
            return

        primary_sub_topic = topics_tree[1]
        specific_sub_topic = topics_tree[-1]
        requested_method = None

        if topic == PORTABLE_DROPBOT_CONNECTED:
            self.portable_dropbot_connection_active = True
            requested_method = f"on_{specific_sub_topic}_signal"

        elif topic == PORTABLE_DROPBOT_DISCONNECTED:
            self.portable_dropbot_connection_active = False
            requested_method = f"on_{specific_sub_topic}_signal"

        elif topic == RETRY_CONNECTION:
            requested_method = f"on_{specific_sub_topic}_request"

        elif primary_sub_topic == "requests":
            if self.portable_dropbot_connection_active:
                requested_method = f"on_{specific_sub_topic}_request"
            else:
                logger.warning(
                    f"Request for '{specific_sub_topic}' denied: "
                    f"Portable Dropbot is disconnected.")

        if requested_method:
            if self.timestamps.get(topic, datetime.min) \
                    > timestamped_message.timestamp_dt:
                return
            self.timestamps[topic] = timestamped_message.timestamp_dt
            err_msg = invoke_class_method(self, requested_method,
                                          timestamped_message)
            if err_msg:
                logger.error(f"Error handling topic {topic}: {err_msg}")

    def traits_init(self):
        logger.info("Starting PortableDropbotController listener")
        self.dramatiq_listener_actor = \
            generate_class_method_dramatiq_listener_actor(
                listener_name=self.listener_name,
                class_method=self.listener_actor_routine,
            )

    # ------------------------------------------------------------------ #
    # Publish helpers                                                      #
    # ------------------------------------------------------------------ #
    def _publish_connected(self):
        publish_message(topic=PORTABLE_DROPBOT_CONNECTED, message="True")

    def _publish_disconnected(self):
        publish_message(topic=PORTABLE_DROPBOT_DISCONNECTED,
                        message="True")

    def _publish_realtime_mode(self):
        publish_message(topic=REALTIME_MODE_UPDATED,
                        message="True" if self.realtime_mode else "False")

    def _publish_error(self, context, error):
        logger.error(f"Portable Dropbot {context} failed: {error}")
        publish_message(topic=ERROR_RAISED, message=json.dumps(
            {"context": context, "error": str(error)}))

    def _publish_alarm(self, cmd, alarms):
        """Wired into the driver's on_alarm callback: the decoded
        alarm strings, straight to whoever is showing status."""
        publish_message(topic=ALARM_RAISED, message=json.dumps(
            {"command": str(cmd), "alarms": list(alarms)}))

    # ------------------------------------------------------------------ #
    # Guarded driver access                                                #
    # ------------------------------------------------------------------ #
    def _proxy_call(self, context, call):
        """Run one driver call; an OS/serial-level failure means the
        device is gone (disconnect + rescan), anything else is
        reported as an error signal rather than a traceback. Returns
        (ok, result)."""
        if self.proxy is None:
            logger.warning(f"Portable Dropbot not connected: "
                           f"ignoring {context}.")
            return False, None
        try:
            return True, call()
        except OSError as error:
            logger.warning(f"Portable Dropbot vanished during "
                           f"{context}: {error}")
            self.on_disconnected_signal("")
            return False, None
        except Exception as error:
            self._publish_error(context, error)
            return False, None

    # ------------------------------------------------------------------ #
    # Status / motor snapshots                                             #
    # ------------------------------------------------------------------ #
    #: Raw u16 status fields carried as value × 100 on the wire (the
    #: driver's own SysStatusSignalBoard.to_dict scaling).
    _SCALED_STATUS_FIELDS = ("cur_temp", "target_temp", "hv_vol",
                             "dev_temp", "dev_hum")

    def _publish_status_snapshot(self):
        """One driver status read fans out to both panes: the signal
        board's readings (HV, temps, chip detect...) on STATUS_UPDATED
        and the motor picture on MOTORS_UPDATED. Scaled to engineering
        units here, so the panes never learn the wire encoding."""
        ok, status = self._proxy_call("status read",
                                      lambda: self.proxy.status)
        if not ok or not isinstance(status, dict):
            return
        signal = dict(status.get("signal", {}))
        for field in self._SCALED_STATUS_FIELDS:
            if field in signal:
                signal[field] = signal[field] / 100.0
        if "chip_on_pad" in signal:
            signal["chip_on_pad"] = signal["chip_on_pad"] == 1
        publish_message(topic=STATUS_UPDATED, message=json.dumps(signal))
        self._publish_motors(mechanisms=status.get("motor", {}))

    def _publish_motors(self, mechanisms=None):
        ok, positions = self._proxy_call(
            "motor positions", lambda: self.proxy.uart.getMotorPositions())
        ok_homed, homed = self._proxy_call(
            "motor homed flags",
            lambda: self.proxy.uart.getMotorHomedStatus())
        payload = {
            "positions": {name: positions[index]
                          for name, index in MOTOR_IDS.items()
                          if ok and positions is not None
                          and index < len(positions)},
            "homed": dict(homed) if ok_homed and homed else {},
            "mechanisms": mechanisms if mechanisms is not None else {},
        }
        publish_message(topic=MOTORS_UPDATED, message=json.dumps(payload))

    def _apply_actuation(self):
        """Push the current HV setpoints (both Int) to the device."""
        self._proxy_call(
            "set actuation",
            lambda: self.proxy.set_actuation(int(self.voltage),
                                             int(self.frequency)))

    def _apply_light_intensity(self):
        """Push the illumination LED brightness (%) to the device."""
        self._proxy_call(
            "set light intensity",
            lambda: self.proxy.uart.setLEDIntensity(
                int(self.light_intensity), fluorescence=False))

    # ------------------------------------------------------------------ #
    # Shared-signal handlers                                               #
    # ------------------------------------------------------------------ #
    def on_connected_signal(self, message):
        self.portable_dropbot_connection_active = True

    def on_disconnected_signal(self, message):
        self.portable_dropbot_connection_active = False
        if self.proxy is not None:
            try:
                self.proxy.disconnect()
            except Exception:
                pass
            self.proxy = None
