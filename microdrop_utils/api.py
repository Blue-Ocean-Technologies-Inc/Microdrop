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


# ---------------------------------------------------------------------------
# Source imports — all topic values come from plugin consts.py modules
# ---------------------------------------------------------------------------
from dropbot_controller import consts as _dropbot
from electrode_controller import consts as _electrode
from protocol_grid import consts as _protocol
from device_viewer import consts as _device_viewer
from microdrop_application import consts as _app
from peripheral_controller import consts as _peripheral
from ssh_controls import consts as _ssh
from opendrop_controller import consts as _opendrop
from pgva_controller_plugin import consts as _pgva
from mock_dropbot_controller import consts as _mock
from dropbot_preferences_ui import consts as _prefs_ui


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
        CAPACITANCE_UPDATED     = _dropbot.CAPACITANCE_UPDATED
        SHORTS_DETECTED         = _dropbot.SHORTS_DETECTED
        HALTED                  = _dropbot.HALTED
        CHIP_INSERTED           = _dropbot.CHIP_INSERTED
        SELF_TESTS_PROGRESS     = _dropbot.SELF_TESTS_PROGRESS
        DROPLETS_DETECTED       = _dropbot.DROPLETS_DETECTED

    class Warnings:
        """Warning-level signals published by the backend."""
        NO_DROPBOT_AVAILABLE    = _dropbot.NO_DROPBOT_AVAILABLE
        NO_POWER                = _dropbot.NO_POWER

    class Requests:
        """Topics consumed by the backend -- send these to request an action."""
        START_DEVICE_MONITORING             = _dropbot.START_DEVICE_MONITORING
        DETECT_SHORTS                       = _dropbot.DETECT_SHORTS
        RETRY_CONNECTION                    = _dropbot.RETRY_CONNECTION
        HALT                                = _dropbot.HALT
        SET_VOLTAGE                         = _dropbot.SET_VOLTAGE
        SET_FREQUENCY                       = _dropbot.SET_FREQUENCY
        RUN_ALL_TESTS                       = _dropbot.RUN_ALL_TESTS
        TEST_VOLTAGE                        = _dropbot.TEST_VOLTAGE
        TEST_ON_BOARD_FEEDBACK_CALIBRATION  = _dropbot.TEST_ON_BOARD_FEEDBACK_CALIBRATION
        TEST_SHORTS                         = _dropbot.TEST_SHORTS
        TEST_CHANNELS                       = _dropbot.TEST_CHANNELS
        CHIP_CHECK                          = _dropbot.CHIP_CHECK
        SELF_TEST_CANCEL                    = _dropbot.SELF_TEST_CANCEL
        DETECT_DROPLETS                     = _dropbot.DETECT_DROPLETS
        CHANGE_SETTINGS                     = _dropbot.CHANGE_SETTINGS

    class Errors:
        """Error topics for the DropBot domain."""
        DROPBOT_ERROR           = _dropbot.DROPBOT_ERROR


# ---------------------------------------------------------------------------
# Hardware Topics  (shared across dropbot_controller & electrode_controller)
# ---------------------------------------------------------------------------

class HardwareTopics:
    """Cross-cutting hardware topics used by multiple controller plugins."""

    class Signals:
        """Signals emitted by hardware backends."""
        CONNECTED                 = _dropbot.DROPBOT_CONNECTED
        DISCONNECTED              = _dropbot.DROPBOT_DISCONNECTED
        REALTIME_MODE_UPDATED     = _dropbot.REALTIME_MODE_UPDATED
        DISABLED_CHANNELS_CHANGED = _dropbot.DISABLED_CHANNELS_CHANGED

    class Requests:
        """Requests accepted by hardware backends."""
        ELECTRODES_STATE_CHANGE = _electrode.ELECTRODES_STATE_CHANGE
        ELECTRODES_DISABLE      = _electrode.ELECTRODES_DISABLE_REQUEST
        SET_REALTIME_MODE       = _dropbot.SET_REALTIME_MODE


# ---------------------------------------------------------------------------
# UI Topics  (protocol_grid/consts.py, dropbot_preferences_ui/consts.py)
# ---------------------------------------------------------------------------

class UITopics:
    """Topics for UI state synchronisation between frontend plugins."""

    DEVICE_VIEWER_STATE_CHANGED     = _device_viewer.DEVICE_VIEWER_STATE_CHANGED
    PROTOCOL_GRID_DISPLAY_STATE     = _protocol.PROTOCOL_GRID_DISPLAY_STATE
    CALIBRATION_DATA                = _protocol.CALIBRATION_DATA
    DEVICE_VIEWER_SCREEN_CAPTURE    = _device_viewer.DEVICE_VIEWER_SCREEN_CAPTURE
    DEVICE_VIEWER_SCREEN_RECORDING  = _device_viewer.DEVICE_VIEWER_SCREEN_RECORDING
    DEVICE_VIEWER_CAMERA_ACTIVE     = _device_viewer.DEVICE_VIEWER_CAMERA_ACTIVE
    DEVICE_VIEWER_MEDIA_CAPTURED    = _device_viewer.DEVICE_VIEWER_MEDIA_CAPTURED
    DEVICE_VIEWER_RECORDING_STATE   = _protocol.DEVICE_VIEWER_RECORDING_STATE
    ROUTES_EXECUTING                = _protocol.ROUTES_EXECUTING
    VOLTAGE_FREQUENCY_RANGE_CHANGED = _prefs_ui.VOLTAGE_FREQUENCY_RANGE_CHANGED


# ---------------------------------------------------------------------------
# Application-level Topics  (microdrop_application/consts.py)
# ---------------------------------------------------------------------------

class ApplicationTopics:
    """Application-wide topics published by the core MicroDrop plugin."""
    ADVANCED_MODE_CHANGE    = _app.ADVANCED_MODE_CHANGE
    PROTOCOL_RUNNING        = _protocol.PROTOCOL_RUNNING


# ---------------------------------------------------------------------------
# Peripheral / ZStage Controller  (peripheral_controller/consts.py)
# ---------------------------------------------------------------------------

class ZStageTopics:
    """Topics for the ZStage peripheral (MR-Box magnets / z-stage)."""

    DEVICE_NAME = _peripheral.DEVICE_NAME

    class Signals:
        """Signals emitted by the ZStage backend."""
        CONNECTED           = _peripheral.CONNECTED
        DISCONNECTED        = _peripheral.DISCONNECTED
        POSITION_UPDATED    = _peripheral.ZSTAGE_POSITION_UPDATED

    class Requests:
        """Requests accepted by the ZStage backend."""
        START_DEVICE_MONITORING = _peripheral.START_DEVICE_MONITORING
        GO_HOME                 = _peripheral.GO_HOME
        MOVE_UP                 = _peripheral.MOVE_UP
        MOVE_DOWN               = _peripheral.MOVE_DOWN
        SET_POSITION            = _peripheral.SET_POSITION
        RETRY_CONNECTION        = _peripheral.RETRY_CONNECTION
        UPDATE_CONFIG           = _peripheral.UPDATE_CONFIG

    class Errors:
        """Error topics for the ZStage domain."""
        ERROR               = _peripheral.ERROR


# ---------------------------------------------------------------------------
# SSH Controls  (ssh_controls/consts.py)
# ---------------------------------------------------------------------------

class SSHTopics:
    """Topics for the SSH key management service."""

    class Requests:
        """Requests accepted by the SSH controls backend."""
        GENERATE_KEYPAIR            = _ssh.GENERATE_KEYPAIR
        KEY_UPLOAD                  = _ssh.KEY_UPLOAD
        SYNC_EXPERIMENTS            = _ssh.SYNC_EXPERIMENTS_REQUEST

    class Started:
        """Progress signals published by the SSH controls service."""
        SYNC_EXPERIMENTS_STARTED    = _ssh.SYNC_EXPERIMENTS_STARTED

    class Success:
        """Success signals published by the SSH controls backend."""
        SSH_KEYGEN_SUCCESS          = _ssh.SSH_KEYGEN_SUCCESS
        SSH_KEY_UPLOAD_SUCCESS      = _ssh.SSH_KEY_UPLOAD_SUCCESS
        SYNC_EXPERIMENTS_SUCCESS    = _ssh.SYNC_EXPERIMENTS_SUCCESS

    class Warnings:
        """Warning signals published by the SSH controls backend."""
        SSH_KEYGEN_WARNING          = _ssh.SSH_KEYGEN_WARNING

    class Errors:
        """Error signals published by the SSH controls backend."""
        SSH_KEYGEN_ERROR            = _ssh.SSH_KEYGEN_ERROR
        SSH_KEY_UPLOAD_ERROR        = _ssh.SSH_KEY_UPLOAD_ERROR
        SYNC_EXPERIMENTS_ERROR      = _ssh.SYNC_EXPERIMENTS_ERROR


# ---------------------------------------------------------------------------
# OpenDrop Controller  (opendrop_controller/consts.py)
# ---------------------------------------------------------------------------

class OpenDropTopics:
    """Topics owned by the OpenDrop controller plugin."""

    class Signals:
        """Signals emitted by the OpenDrop backend."""
        TEMPERATURES_UPDATED    = _opendrop.OPENDROP_TEMPERATURES_UPDATED
        FEEDBACK_UPDATED        = _opendrop.OPENDROP_FEEDBACK_UPDATED
        BOARD_INFO              = _opendrop.OPENDROP_BOARD_INFO

    class Requests:
        """Requests accepted by the OpenDrop backend."""
        RETRY_CONNECTION    = _opendrop.RETRY_CONNECTION
        SET_FEEDBACK        = _opendrop.SET_FEEDBACK
        SET_TEMPERATURES    = _opendrop.SET_TEMPERATURES
        SET_TEMPERATURE_1   = _opendrop.SET_TEMPERATURE_1
        SET_TEMPERATURE_2   = _opendrop.SET_TEMPERATURE_2
        SET_TEMPERATURE_3   = _opendrop.SET_TEMPERATURE_3
        CHANGE_SETTINGS     = _opendrop.CHANGE_SETTINGS


# ---------------------------------------------------------------------------
# PGVA Controller  (pgva_controller_plugin/consts.py)
# ---------------------------------------------------------------------------

class PGVATopics:
    """Topics owned by the PGVA (Pressure/Vacuum) controller plugin."""

    class Signals:
        """Signals emitted by the PGVA backend."""
        CONNECTED                    = _pgva.PGVA_CONNECTED
        DISCONNECTED                 = _pgva.PGVA_DISCONNECTED
        PRESSURE_UPDATED             = _pgva.PGVA_PRESSURE_UPDATED
        VACUUM_UPDATED               = _pgva.PGVA_VACUUM_UPDATED
        OUTPUT_PRESSURE_UPDATED      = _pgva.PGVA_OUTPUT_PRESSURE_UPDATED
        STATUS_UPDATED               = _pgva.PGVA_STATUS_UPDATED
        WARNINGS_UPDATED             = _pgva.PGVA_WARNINGS_UPDATED
        ERRORS_UPDATED               = _pgva.PGVA_ERRORS_UPDATED
        COMPREHENSIVE_STATUS_UPDATED = _pgva.PGVA_COMPREHENSIVE_STATUS_UPDATED
        HEALTH_CHECK_UPDATED         = _pgva.PGVA_HEALTH_CHECK_UPDATED
        DEVICE_INFO_UPDATED          = _pgva.PGVA_DEVICE_INFO_UPDATED
        ERROR                        = _pgva.PGVA_ERROR_SIGNAL

    class Requests:
        """Requests accepted by the PGVA backend."""
        SET_PRESSURE            = _pgva.SET_PRESSURE
        SET_VACUUM              = _pgva.SET_VACUUM
        SET_OUTPUT_PRESSURE     = _pgva.SET_OUTPUT_PRESSURE
        GET_PRESSURE            = _pgva.GET_PRESSURE
        GET_VACUUM              = _pgva.GET_VACUUM
        GET_OUTPUT_PRESSURE     = _pgva.GET_OUTPUT_PRESSURE
        GET_STATUS              = _pgva.GET_STATUS
        GET_WARNINGS            = _pgva.GET_WARNINGS
        GET_ERRORS              = _pgva.GET_ERRORS
        GET_COMPREHENSIVE_STATUS = _pgva.GET_COMPREHENSIVE_STATUS
        GET_HEALTH_CHECK        = _pgva.GET_HEALTH_CHECK
        GET_DEVICE_INFO         = _pgva.GET_DEVICE_INFO
        ENABLE                  = _pgva.ENABLE_PGVA
        DISABLE                 = _pgva.DISABLE_PGVA
        RESET                   = _pgva.RESET_PGVA
        TRIGGER_MANUAL          = _pgva.TRIGGER_MANUAL
        STORE_TO_EEPROM         = _pgva.STORE_TO_EEPROM
        CONNECT                 = _pgva.CONNECT_PGVA
        DISCONNECT              = _pgva.DISCONNECT_PGVA


# ---------------------------------------------------------------------------
# Mock DropBot Controller  (mock_dropbot_controller/consts.py)
# ---------------------------------------------------------------------------

class MockDropbotTopics:
    """Topics owned by the mock DropBot controller (for testing without hardware)."""

    class Requests:
        """Requests accepted by the mock DropBot backend."""
        CHANGE_SIM_SETTINGS     = _mock.MOCK_CHANGE_SIM_SETTINGS
        SIMULATE_CONNECT        = _mock.MOCK_SIMULATE_CONNECT
        SIMULATE_DISCONNECT     = _mock.MOCK_SIMULATE_DISCONNECT
        SIMULATE_CHIP_INSERT    = _mock.MOCK_SIMULATE_CHIP_INSERT
        SIMULATE_SHORTS         = _mock.MOCK_SIMULATE_SHORTS
        SIMULATE_HALT           = _mock.MOCK_SIMULATE_HALT

    class Signals:
        """Signals emitted by the mock DropBot backend."""
        ACTUATED_CHANNELS_UPDATED   = _mock.MOCK_ACTUATED_CHANNELS_UPDATED
        STREAM_STATUS_UPDATED       = _mock.MOCK_STREAM_STATUS_UPDATED


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
