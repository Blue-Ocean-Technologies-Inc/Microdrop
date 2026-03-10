import json
import random
from datetime import datetime, UTC

import dramatiq
from traits.api import HasTraits, Instance, Bool, Str, Float, Int, Set, Dict

from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
    invoke_class_method,
    TimestampedMessage,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger

from .consts import (
    PKG, CHIP_INSERTED, CAPACITANCE_UPDATED, HALTED, SHORTS_DETECTED,
    DROPBOT_CONNECTED, DROPBOT_DISCONNECTED, DROPLETS_DETECTED,
    REALTIME_MODE_UPDATED, SELF_TESTS_PROGRESS,
    START_DEVICE_MONITORING, RETRY_CONNECTION, CHANGE_SETTINGS,
    SET_REALTIME_MODE, HALT,
    TestEvent, create_test_progress_message,
    DEFAULT_BASE_CAPACITANCE_PF, DEFAULT_CAPACITANCE_DELTA_PF,
    DEFAULT_CAPACITANCE_NOISE_PF, DEFAULT_STREAM_INTERVAL_MS,
    DEFAULT_VOLTAGE, DEFAULT_FREQUENCY, DEFAULT_NUM_CHANNELS,
)

logger = get_logger(__name__, level="INFO")


class MockDropbotController(HasTraits):
    """
    A mock DropBot controller that emulates all hardware communication.

    Subscribes to the same request topics as the real DropBot controller
    and publishes mock responses in identical message formats.
    """

    # ---- Dramatiq listener ----
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str(f"{PKG}_listener")
    timestamps = Dict(str, datetime)

    # ---- Mock device state ----
    connected = Bool(False)
    realtime_mode = Bool(False)
    chip_inserted = Bool(False)
    voltage = Float(DEFAULT_VOLTAGE)
    frequency = Float(DEFAULT_FREQUENCY)
    actuated_channels = Set(Int)
    num_channels = Int(DEFAULT_NUM_CHANNELS)

    # ---- Capacitance simulation settings ----
    base_capacitance_pf = Float(DEFAULT_BASE_CAPACITANCE_PF)
    capacitance_delta_pf = Float(DEFAULT_CAPACITANCE_DELTA_PF)
    capacitance_noise_pf = Float(DEFAULT_CAPACITANCE_NOISE_PF)

    # ---- Stream control ----
    stream_active = Bool(False)
    stream_interval_ms = Int(DEFAULT_STREAM_INTERVAL_MS)
    _stream_timer = Instance('PySide6.QtCore.QTimer')

    # ---- Lifecycle ----

    def traits_init(self):
        logger.info("Starting MockDropbotController listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )

    def cleanup(self):
        logger.info("Cleaning up MockDropbotController resources")
        self.stop_stream()

    # ---- Dramatiq listener dispatch ----

    def listener_actor_routine(self, timestamped_message: TimestampedMessage, topic: str):
        logger.debug(f"MOCK DROPBOT LISTENER: '{timestamped_message}' from topic: {topic}")

        topics_tree = topic.split("/")
        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1]
        specific_sub_topic = topics_tree[-1]

        requested_method = None

        if head_topic in ['dropbot', 'hardware']:
            if topic in [DROPBOT_CONNECTED, DROPBOT_DISCONNECTED]:
                requested_method = f"on_{specific_sub_topic}_signal"
            elif topic in [START_DEVICE_MONITORING, RETRY_CONNECTION, CHANGE_SETTINGS]:
                requested_method = f"on_{specific_sub_topic}_request"
            elif primary_sub_topic == 'requests':
                if self.connected:
                    requested_method = f"on_{specific_sub_topic}_request"
                else:
                    logger.warning(f"Mock: Request for {specific_sub_topic} denied: not connected.")

        if requested_method:
            if self.timestamps.get(topic, datetime.min) > timestamped_message.timestamp_dt:
                return
            self.timestamps[topic] = timestamped_message.timestamp_dt

            err_msg = invoke_class_method(self, requested_method, timestamped_message)
            if err_msg:
                logger.error(f"Mock handler error: {err_msg}")

    # ---- Request handlers ----

    def on_start_device_monitoring_request(self, message):
        logger.info("Mock: Simulating device discovery...")
        self.connected = True
        publish_message(topic=DROPBOT_CONNECTED, message="mock_dropbot")

    def on_connected_signal(self, message):
        self.connected = True

    def on_disconnected_signal(self, message):
        self.connected = False
        self.realtime_mode = False
        self.stop_stream()

    def on_retry_connection_request(self, message):
        self.on_start_device_monitoring_request(message)

    def on_chip_check_request(self, message):
        publish_message(topic=CHIP_INSERTED, message=str(self.chip_inserted))

    def on_set_voltage_request(self, message):
        try:
            v = float(message)
            if 30 <= v <= 150:
                self.voltage = v
                logger.info(f"Mock: Voltage set to {v} V")
            else:
                logger.error("Mock: Voltage must be between 30 and 150 V")
        except (ValueError, TypeError) as e:
            logger.error(f"Mock: Invalid voltage: {e}")

    def on_set_frequency_request(self, message):
        try:
            f = float(message)
            if 100 <= f <= 20000:
                self.frequency = f
                logger.info(f"Mock: Frequency set to {f} Hz")
            else:
                logger.error("Mock: Frequency must be between 100 and 20000 Hz")
        except (ValueError, TypeError) as e:
            logger.error(f"Mock: Invalid frequency: {e}")

    def on_set_realtime_mode_request(self, message):
        if message == "True":
            self.realtime_mode = True
            publish_message(topic=REALTIME_MODE_UPDATED, message="True")
            self.start_stream()
        else:
            self.realtime_mode = False
            publish_message(topic=REALTIME_MODE_UPDATED, message="False")
            self.stop_stream()
        logger.info(f"Mock: Realtime mode set to {self.realtime_mode}")

    def on_electrodes_state_change_request(self, message: str):
        try:
            data = json.loads(message)
            channels = set(data.get("actuated_channels", []))
            invalid = {ch for ch in channels if ch < 0 or ch >= self.num_channels}
            if invalid:
                logger.error(f"Mock: Invalid channel indices: {invalid}")
                return
            self.actuated_channels = channels
            logger.info(f"Mock: {len(channels)} channels actuated: {sorted(channels)}")
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Mock: Invalid electrode state message: {e}")

    def on_detect_shorts_request(self, message):
        publish_message(
            topic=SHORTS_DETECTED,
            message=json.dumps({"Shorts_detected": [], "Show_window": True}),
        )
        logger.info("Mock: No shorts detected (mock)")

    def on_detect_droplets_request(self, message):
        publish_message(
            topic=DROPLETS_DETECTED,
            message=json.dumps({
                "success": True,
                "detected_channels": sorted(self.actuated_channels),
                "error_message": "",
            }),
        )

    def on_halt_request(self, message):
        logger.warning("Mock: Halt received, resetting channels")
        self.actuated_channels = set()
        self.realtime_mode = False
        publish_message(topic=SET_REALTIME_MODE, message="False")

    def on_run_all_tests_request(self, message):
        tests = ["test_voltage", "test_on_board_feedback_calibration", "test_shorts", "test_channels"]
        publish_message(topic=SELF_TESTS_PROGRESS,
                        message=create_test_progress_message(TestEvent.SESSION_START))
        for i, test_name in enumerate(tests):
            publish_message(topic=SELF_TESTS_PROGRESS,
                            message=create_test_progress_message(
                                TestEvent.PROGRESS, test_name=test_name, test_index=i, status="completed"))
        publish_message(topic=SELF_TESTS_PROGRESS,
                        message=create_test_progress_message(TestEvent.SESSION_END, status="completed"))

    def on_test_voltage_request(self, message):
        publish_message(topic=SELF_TESTS_PROGRESS,
                        message=create_test_progress_message(
                            TestEvent.PROGRESS, test_name="test_voltage", test_index=0, status="completed"))

    def on_test_on_board_feedback_calibration_request(self, message):
        publish_message(topic=SELF_TESTS_PROGRESS,
                        message=create_test_progress_message(
                            TestEvent.PROGRESS, test_name="test_on_board_feedback_calibration",
                            test_index=1, status="completed"))

    def on_test_shorts_request(self, message):
        publish_message(topic=SELF_TESTS_PROGRESS,
                        message=create_test_progress_message(
                            TestEvent.PROGRESS, test_name="test_shorts", test_index=2, status="completed"))

    def on_test_channels_request(self, message):
        publish_message(topic=SELF_TESTS_PROGRESS,
                        message=create_test_progress_message(
                            TestEvent.PROGRESS, test_name="test_channels", test_index=3, status="completed"))

    def on_self_test_cancel_request(self, message):
        publish_message(topic=SELF_TESTS_PROGRESS,
                        message=create_test_progress_message(TestEvent.SESSION_END, status="cancelled"))

    def on_change_settings_request(self, message):
        logger.info(f"Mock: Settings change request received: {message}")

    # ---- Capacitance stream ----

    def _compute_mock_capacitance(self) -> float:
        base = self.base_capacitance_pf
        actuated_contribution = len(self.actuated_channels) * self.capacitance_delta_pf
        noise = random.uniform(-self.capacitance_noise_pf, self.capacitance_noise_pf)
        return base + actuated_contribution + noise

    def _publish_capacitance(self):
        if not self.realtime_mode:
            return
        cap_pf = self._compute_mock_capacitance()
        utc_timestamp = datetime.now(UTC).timestamp()
        publish_message(
            topic=CAPACITANCE_UPDATED,
            message=json.dumps({
                "capacitance": f"{cap_pf:.4g} pF",
                "voltage": f"{self.voltage:.3g} V",
                "instrument_time_us": int(utc_timestamp * 1e6),
                "reception_time": utc_timestamp,
            }),
        )

    def start_stream(self):
        if self._stream_timer is not None:
            self._stream_timer.stop()
        from PySide6.QtCore import QTimer
        self._stream_timer = QTimer()
        self._stream_timer.timeout.connect(self._publish_capacitance)
        self._stream_timer.start(self.stream_interval_ms)
        self.stream_active = True
        logger.info(f"Mock: Capacitance stream started ({self.stream_interval_ms}ms interval)")

    def stop_stream(self):
        if self._stream_timer is not None:
            self._stream_timer.stop()
            self._stream_timer = None
        self.stream_active = False
        logger.info("Mock: Capacitance stream stopped")

    def restart_stream(self):
        if self.stream_active:
            self.stop_stream()
            self.start_stream()

    # ---- Simulation helpers (called from UI) ----

    def simulate_chip_insert(self, inserted: bool):
        self.chip_inserted = inserted
        publish_message(topic=CHIP_INSERTED, message=str(inserted))
        logger.info(f"Mock: Chip {'inserted' if inserted else 'removed'}")

    def simulate_shorts(self, channels: list):
        publish_message(
            topic=SHORTS_DETECTED,
            message=json.dumps({"Shorts_detected": channels, "Show_window": True}),
        )
        logger.info(f"Mock: Simulated shorts on channels {channels}")

    def simulate_halt(self, error_name: str = "output-current-exceeded"):
        reasons = {
            "output-current-exceeded": (
                "because output current was exceeded",
                "All channels have been disabled and high voltage has been "
                "turned off until the DropBot is restarted.",
            ),
            "chip-load-saturated": (
                "because chip load feedback exceeded allowable range",
                "Requested channels cannot be actuated.",
            ),
        }
        reason, msg = reasons.get(error_name, ("unknown", "Unknown halt reason"))
        halted_message = json.dumps({"name": error_name, "reason": reason, "message": msg})
        publish_message(topic=HALTED, message=halted_message)
        publish_message(topic=HALT, message=halted_message)
        logger.warning(f"Mock: Simulated halt ({error_name})")
