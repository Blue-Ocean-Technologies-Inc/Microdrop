"""
Microdrop Messaging API
=======================

Centralized access to all Dramatiq pub/sub message topics, publishing utilities,
and subscription helpers used throughout the MicroDrop application.

This module serves as the single import point for any code that needs to publish
or subscribe to messages. It re-exports every topic constant from the individual
plugin ``consts.py`` modules and the core messaging primitives from
``dramatiq_pub_sub_helpers``.

Topic Naming Conventions
------------------------
Topics follow MQTT-style hierarchical naming with ``/`` delimiters::

    <domain>/signals/<event_name>   -- emitted when something happens (backend -> frontend)
    <domain>/requests/<action_name> -- request an action be performed   (frontend -> backend)
    <domain>/error                  -- error notification

MQTT wildcards are supported for subscriptions only (not publishing):

- ``+`` matches a single level  (e.g. ``dropbot/signals/+``)
- ``#`` matches all sub-levels  (e.g. ``dropbot/signals/#``)

Quick Start
-----------
Publishing a simple message::

    from microdrop_utils.api import publish_message, DropbotTopics
    publish_message(message="100", topic=DropbotTopics.Requests.SET_VOLTAGE)

Publishing with Pydantic validation::

    from microdrop_utils.api import ValidatedTopicPublisher
    from electrode_controller.models import ElectrodeChannelsRequest

    publisher = ValidatedTopicPublisher(
        topic="hardware/requests/electrodes_state_change",
        validator_class=ElectrodeChannelsRequest,
    )
    publisher.publish({"channels": {1, 2, 3}}, validation_context={"max_channels": 120})

Handler Naming
--------------
Frontend handlers (``DramatiqControllerBase``):
    Methods named ``_on_{last_topic_segment}_triggered()`` are called reflectively.

Backend handlers (``DropbotControllerBase``):
    Methods named ``on_{last_topic_segment}_request()`` or ``on_{last_topic_segment}_signal()``.
"""

from logger.logger_service import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Core messaging primitives
# ---------------------------------------------------------------------------
from microdrop_utils.dramatiq_pub_sub_helpers import (  # noqa: E402
    publish_message,
    ValidatedTopicPublisher,
    MessageRouterActor,
    MessageRouterData,
    MQTTMatcher,
)
from microdrop_utils.dramatiq_controller_base import (  # noqa: E402
    DramatiqControllerBase,
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)


# ===================================================================
# Topic Constants -- organised by domain / plugin
# ===================================================================

# ---------------------------------------------------------------------------
# Dropbot Controller  (dropbot_controller/consts.py)
# ---------------------------------------------------------------------------

class DropbotTopics:
    """All topics owned by the DropBot controller plugin."""

    class Signals:
        """Topics emitted by the backend when hardware events occur."""
        CAPACITANCE_UPDATED     = "dropbot/signals/capacitance_updated"
        SHORTS_DETECTED         = "dropbot/signals/shorts_detected"
        HALTED                  = "dropbot/signals/halted"
        CHIP_INSERTED           = "dropbot/signals/chip_inserted"
        CHIP_NOT_INSERTED       = "dropbot/signals/chip_not_inserted"
        SELF_TESTS_PROGRESS     = "dropbot/signals/self_tests_progress"
        DROPLETS_DETECTED       = "dropbot/signals/drops_detected"

    class Warnings:
        """Warning-level signals published by the backend."""
        NO_DROPBOT_AVAILABLE    = "dropbot/signals/warnings/no_dropbot_available"
        NO_POWER                = "dropbot/signals/warnings/no_power"

    class Requests:
        """Topics consumed by the backend -- send these to request an action."""
        START_DEVICE_MONITORING             = "dropbot/requests/start_device_monitoring"
        DETECT_SHORTS                       = "dropbot/requests/detect_shorts"
        RETRY_CONNECTION                    = "dropbot/requests/retry_connection"
        HALT                                = "dropbot/requests/halt"
        SET_VOLTAGE                         = "dropbot/requests/set_voltage"
        SET_FREQUENCY                       = "dropbot/requests/set_frequency"
        RUN_ALL_TESTS                       = "dropbot/requests/run_all_tests"
        TEST_VOLTAGE                        = "dropbot/requests/test_voltage"
        TEST_ON_BOARD_FEEDBACK_CALIBRATION  = "dropbot/requests/test_on_board_feedback_calibration"
        TEST_SHORTS                         = "dropbot/requests/test_shorts"
        TEST_CHANNELS                       = "dropbot/requests/test_channels"
        CHIP_CHECK                          = "dropbot/requests/chip_check"
        SELF_TEST_CANCEL                    = "dropbot/requests/self_test_cancel"
        DETECT_DROPLETS                     = "dropbot/requests/detect_droplets"
        CHANGE_SETTINGS                     = "dropbot/requests/change_settings"

    class Errors:
        """Error topics for the DropBot domain."""
        DROPBOT_ERROR           = "dropbot/error"


# ---------------------------------------------------------------------------
# Hardware Topics  (shared across dropbot_controller & electrode_controller)
# ---------------------------------------------------------------------------

class HardwareTopics:
    """Cross-cutting hardware topics used by multiple controller plugins."""

    class Signals:
        """Signals emitted by hardware backends."""
        CONNECTED               = "hardware/signals/connected"
        DISCONNECTED            = "hardware/signals/disconnected"
        REALTIME_MODE_UPDATED   = "hardware/signals/realtime_mode_updated"
        DISABLED_CHANNELS_CHANGED = "hardware/signals/disabled_channels_changed"

    class Requests:
        """Requests accepted by hardware backends."""
        ELECTRODES_STATE_CHANGE = "hardware/requests/electrodes_state_change"
        ELECTRODES_DISABLE      = "hardware/requests/electrodes_disable"
        SET_REALTIME_MODE       = "hardware/requests/set_realtime_mode"


# ---------------------------------------------------------------------------
# UI Topics  (protocol_grid/consts.py, device_viewer)
# ---------------------------------------------------------------------------

class UITopics:
    """Topics for UI state synchronisation between frontend plugins."""

    DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"
    PROTOCOL_GRID_DISPLAY_STATE = "ui/protocol_grid/display_state"
    CALIBRATION_DATA            = "ui/calibration_data"
    DEVICE_VIEWER_SCREEN_CAPTURE    = "ui/device_viewer/screen_capture"
    DEVICE_VIEWER_SCREEN_RECORDING  = "ui/device_viewer/screen_recording"
    DEVICE_VIEWER_CAMERA_ACTIVE     = "ui/device_viewer/camera_active"
    DEVICE_VIEWER_MEDIA_CAPTURED    = "ui/device_viewer/camera/media_captured"
    DEVICE_VIEWER_RECORDING_STATE   = "ui/device_viewer/recording_state"
    ROUTES_EXECUTING                = "ui/device_viewer/routes_executing"


# ---------------------------------------------------------------------------
# Application-level Topics  (microdrop_application/consts.py)
# ---------------------------------------------------------------------------

class ApplicationTopics:
    """Application-wide topics published by the core MicroDrop plugin."""
    ADVANCED_MODE_CHANGE    = "microdrop/advanced_mode_change"
    PROTOCOL_RUNNING        = "microdrop/protocol_running"


# ---------------------------------------------------------------------------
# Peripheral / ZStage Controller  (peripheral_controller/consts.py)
# ---------------------------------------------------------------------------

class ZStageTopics:
    """Topics for the ZStage peripheral (MR-Box magnets / z-stage)."""

    DEVICE_NAME = "ZStage"

    class Signals:
        """Signals emitted by the ZStage backend."""
        CONNECTED           = "ZStage/signals/connected"
        DISCONNECTED        = "ZStage/signals/disconnected"
        POSITION_UPDATED    = "ZStage/signals/position_updated"

    class Requests:
        """Requests accepted by the ZStage backend."""
        START_DEVICE_MONITORING = "ZStage/requests/start_device_monitoring"
        GO_HOME                 = "ZStage/requests/go_home"
        MOVE_UP                 = "ZStage/requests/move_up"
        MOVE_DOWN               = "ZStage/requests/move_down"
        SET_POSITION            = "ZStage/requests/set_position"
        RETRY_CONNECTION        = "ZStage/requests/retry_connection"
        UPDATE_CONFIG           = "ZStage/requests/update_config"

    class Errors:
        """Error topics for the ZStage domain."""
        ERROR               = "ZStage/error"


# ---------------------------------------------------------------------------
# SSH Controls  (ssh_controls/consts.py)
# ---------------------------------------------------------------------------

class SSHTopics:
    """Topics for the SSH key management service."""

    class Requests:
        """Requests accepted by the SSH controls backend."""
        GENERATE_KEYPAIR    = "ssh_service/request/generate_keypair"
        KEY_UPLOAD          = "ssh_service/request/key_upload"

    class Success:
        """Success signals published by the SSH controls backend."""
        SSH_KEYGEN_SUCCESS      = "ssh_service/success/ssh_keygen_success"
        SSH_KEY_UPLOAD_SUCCESS  = "ssh_service/success/ssh_key_upload_success"

    class Warnings:
        """Warning signals published by the SSH controls backend."""
        SSH_KEYGEN_WARNING  = "ssh_service/warning/ssh_keygen_warning"

    class Errors:
        """Error signals published by the SSH controls backend."""
        SSH_KEYGEN_ERROR        = "ssh_service/error/ssh_keygen_error"
        SSH_KEY_UPLOAD_ERROR    = "ssh_service/error/ssh_key_upload_error"


# ---------------------------------------------------------------------------
# OpenDrop Controller  (opendrop_controller/consts.py)
# ---------------------------------------------------------------------------

class OpenDropTopics:
    """Topics owned by the OpenDrop controller plugin."""

    class Signals:
        """Signals emitted by the OpenDrop backend."""
        TEMPERATURES_UPDATED    = "opendrop/signals/temperatures_updated"
        FEEDBACK_UPDATED        = "opendrop/signals/feedback_updated"
        BOARD_INFO              = "opendrop/signals/board_info"

    class Requests:
        """Requests accepted by the OpenDrop backend."""
        RETRY_CONNECTION    = "opendrop/requests/retry_connection"
        SET_FEEDBACK        = "opendrop/requests/set_feedback"
        SET_TEMPERATURES    = "opendrop/requests/set_temperatures"
        SET_TEMPERATURE_1   = "opendrop/requests/set_temperature_1"
        SET_TEMPERATURE_2   = "opendrop/requests/set_temperature_2"
        SET_TEMPERATURE_3   = "opendrop/requests/set_temperature_3"
        CHANGE_SETTINGS     = "opendrop/requests/change_settings"


# ---------------------------------------------------------------------------
# PGVA Controller  (pgva_controller_plugin/consts.py)
# ---------------------------------------------------------------------------

class PGVATopics:
    """Topics owned by the PGVA (Pressure/Vacuum) controller plugin."""

    class Signals:
        """Signals emitted by the PGVA backend."""
        CONNECTED                   = "pgva/signals/connected"
        DISCONNECTED                = "pgva/signals/disconnected"
        PRESSURE_UPDATED            = "pgva/signals/pressure_updated"
        VACUUM_UPDATED              = "pgva/signals/vacuum_updated"
        OUTPUT_PRESSURE_UPDATED     = "pgva/signals/output_pressure_updated"
        STATUS_UPDATED              = "pgva/signals/status_updated"
        WARNINGS_UPDATED            = "pgva/signals/warnings_updated"
        ERRORS_UPDATED              = "pgva/signals/errors_updated"
        COMPREHENSIVE_STATUS_UPDATED = "pgva/signals/comprehensive_status_updated"
        HEALTH_CHECK_UPDATED        = "pgva/signals/health_check_updated"
        DEVICE_INFO_UPDATED         = "pgva/signals/device_info_updated"
        ERROR                       = "pgva/signals/error"

    class Requests:
        """Requests accepted by the PGVA backend."""
        SET_PRESSURE            = "pgva/requests/set_pressure"
        SET_VACUUM              = "pgva/requests/set_vacuum"
        SET_OUTPUT_PRESSURE     = "pgva/requests/set_output_pressure"
        GET_PRESSURE            = "pgva/requests/get_pressure"
        GET_VACUUM              = "pgva/requests/get_vacuum"
        GET_OUTPUT_PRESSURE     = "pgva/requests/get_output_pressure"
        GET_STATUS              = "pgva/requests/get_status"
        GET_WARNINGS            = "pgva/requests/get_warnings"
        GET_ERRORS              = "pgva/requests/get_errors"
        GET_COMPREHENSIVE_STATUS = "pgva/requests/get_comprehensive_status"
        GET_HEALTH_CHECK        = "pgva/requests/get_health_check"
        GET_DEVICE_INFO         = "pgva/requests/get_device_info"
        ENABLE                  = "pgva/requests/enable"
        DISABLE                 = "pgva/requests/disable"
        RESET                   = "pgva/requests/reset"
        TRIGGER_MANUAL          = "pgva/requests/trigger_manual"
        STORE_TO_EEPROM         = "pgva/requests/store_to_eeprom"
        CONNECT                 = "pgva/requests/connect"
        DISCONNECT              = "pgva/requests/disconnect"


# ---------------------------------------------------------------------------
# Mock DropBot Controller  (mock_dropbot_controller/consts.py)
# ---------------------------------------------------------------------------

class MockDropbotTopics:
    """Topics owned by the mock DropBot controller (for testing without hardware)."""

    class Requests:
        """Requests accepted by the mock DropBot backend."""
        CHANGE_SIM_SETTINGS     = "mock_dropbot/requests/change_simulation_settings"
        SIMULATE_CONNECT        = "mock_dropbot/requests/simulate_connect"
        SIMULATE_DISCONNECT     = "mock_dropbot/requests/simulate_disconnect"
        SIMULATE_CHIP_INSERT    = "mock_dropbot/requests/simulate_chip_insert"
        SIMULATE_SHORTS         = "mock_dropbot/requests/simulate_shorts"
        SIMULATE_HALT           = "mock_dropbot/requests/simulate_halt"

    class Signals:
        """Signals emitted by the mock DropBot backend."""
        ACTUATED_CHANNELS_UPDATED   = "mock_dropbot/signals/actuated_channels_updated"
        STREAM_STATUS_UPDATED       = "mock_dropbot/signals/stream_status_updated"


# ===================================================================
# Wildcard subscription patterns
# ===================================================================

class WildcardPatterns:
    """Pre-built wildcard subscription patterns commonly used by plugins.

    These are convenience constants for the MQTT-style wildcard subscriptions
    accepted by ``MessageRouterData.add_subscriber_to_topic``.
    """
    ALL_DROPBOT_SIGNALS     = "dropbot/signals/#"
    ALL_DROPBOT_REQUESTS    = "dropbot/requests/#"
    ALL_HARDWARE_SIGNALS    = "hardware/signals/#"
    ALL_HARDWARE_REQUESTS   = "hardware/requests/#"
    ALL_OPENDROP_SIGNALS    = "opendrop/signals/#"
    ALL_OPENDROP_REQUESTS   = "opendrop/requests/#"
    ALL_PGVA_SIGNALS        = "pgva/signals/#"
    ALL_PGVA_REQUESTS       = "pgva/requests/#"
    ALL_MOCK_DROPBOT_SIGNALS    = "mock_dropbot/signals/#"
    ALL_MOCK_DROPBOT_REQUESTS   = "mock_dropbot/requests/#"
    ALL_ZSTAGE_SIGNALS      = "ZStage/signals/#"
    ALL_ZSTAGE_REQUESTS     = "ZStage/requests/#"


# ===================================================================
# Convenience helpers
# ===================================================================

def get_all_topics() -> dict[str, list[str]]:
    """Return a dictionary mapping each domain to its list of topic strings.

    Useful for debugging, documentation generation, or runtime introspection
    of all available topics in the system.

    Returns:
        dict mapping domain name (str) to list of topic strings.
    """
    topics: dict[str, list[str]] = {}

    topic_classes = [
        ("dropbot", DropbotTopics),
        ("hardware", HardwareTopics),
        ("ui", UITopics),
        ("application", ApplicationTopics),
        ("zstage", ZStageTopics),
        ("ssh", SSHTopics),
        ("opendrop", OpenDropTopics),
        ("pgva", PGVATopics),
        ("mock_dropbot", MockDropbotTopics),
    ]

    for domain, cls in topic_classes:
        domain_topics = []
        _collect_string_attrs(cls, domain_topics)
        topics[domain] = sorted(domain_topics)

    return topics


def _collect_string_attrs(cls, result: list[str]) -> None:
    """Recursively collect all string class attributes from *cls* and its nested classes."""
    for name in dir(cls):
        if name.startswith("_"):
            continue
        value = getattr(cls, name)
        if isinstance(value, str) and "/" in value:
            result.append(value)
        elif isinstance(value, type):
            _collect_string_attrs(value, result)


# ===================================================================
# Public API
# ===================================================================

__all__ = [
    # Core messaging primitives
    "publish_message",
    "ValidatedTopicPublisher",
    "MessageRouterActor",
    "MessageRouterData",
    "MQTTMatcher",
    "DramatiqControllerBase",
    "basic_listener_actor_routine",
    "generate_class_method_dramatiq_listener_actor",
    # Topic namespaces
    "DropbotTopics",
    "HardwareTopics",
    "UITopics",
    "ApplicationTopics",
    "ZStageTopics",
    "SSHTopics",
    "OpenDropTopics",
    "PGVATopics",
    "MockDropbotTopics",
    "WildcardPatterns",
    # Helpers
    "get_all_topics",
]
