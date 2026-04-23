"""
Tests for microdrop_utils.api -- the centralised messaging API module.

These tests verify that the API module:
1. Exposes all expected topic constants with correct string values.
2. Re-exports core messaging primitives.
3. The get_all_topics() introspection helper works correctly.
4. Topic classes are consistent with their source-of-truth consts.py modules.
"""

import pytest


# ---------------------------------------------------------------------------
# Import the API under test
# ---------------------------------------------------------------------------
from microdrop_utils.api import (
    # Core primitives
    publish_message,
    ValidatedTopicPublisher,
    MessageRouterActor,
    MessageRouterData,
    MQTTMatcher,
    DramatiqControllerBase,
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
    # Topic namespaces
    DropbotTopics,
    HardwareTopics,
    UITopics,
    ApplicationTopics,
    ZStageTopics,
    SSHTopics,
    OpenDropTopics,
    PGVATopics,
    MockDropbotTopics,
    WildcardPatterns,
    # Helpers
    get_all_topics,
)


# ===================================================================
# 1. Core primitives are importable and have the right types
# ===================================================================

class TestCorePrimitivesExported:

    def test_publish_message_is_callable(self):
        assert callable(publish_message)

    def test_validated_topic_publisher_is_class(self):
        assert isinstance(ValidatedTopicPublisher, type)

    def test_message_router_actor_is_class(self):
        assert isinstance(MessageRouterActor, type)

    def test_message_router_data_is_class(self):
        assert isinstance(MessageRouterData, type)

    def test_mqtt_matcher_is_class(self):
        assert isinstance(MQTTMatcher, type)

    def test_dramatiq_controller_base_is_class(self):
        assert isinstance(DramatiqControllerBase, type)

    def test_basic_listener_actor_routine_is_callable(self):
        assert callable(basic_listener_actor_routine)

    def test_generate_class_method_dramatiq_listener_actor_is_callable(self):
        assert callable(generate_class_method_dramatiq_listener_actor)


# ===================================================================
# 2. Topic constants match their source-of-truth consts.py values
# ===================================================================

class TestDropbotTopicsMatchConsts:
    """Cross-check API topic values against dropbot_controller.consts."""

    def test_signals(self):
        from dropbot_controller.consts import (
            CAPACITANCE_UPDATED, SHORTS_DETECTED, HALTED,
            CHIP_INSERTED, SELF_TESTS_PROGRESS,
            DROPLETS_DETECTED,
        )
        assert DropbotTopics.Signals.CAPACITANCE_UPDATED == CAPACITANCE_UPDATED
        assert DropbotTopics.Signals.SHORTS_DETECTED == SHORTS_DETECTED
        assert DropbotTopics.Signals.HALTED == HALTED
        assert DropbotTopics.Signals.CHIP_INSERTED == CHIP_INSERTED
        assert DropbotTopics.Signals.SELF_TESTS_PROGRESS == SELF_TESTS_PROGRESS
        assert DropbotTopics.Signals.DROPLETS_DETECTED == DROPLETS_DETECTED

    def test_warnings(self):
        from dropbot_controller.consts import NO_DROPBOT_AVAILABLE, NO_POWER
        assert DropbotTopics.Warnings.NO_DROPBOT_AVAILABLE == NO_DROPBOT_AVAILABLE
        assert DropbotTopics.Warnings.NO_POWER == NO_POWER

    def test_requests(self):
        from dropbot_controller.consts import (
            START_DEVICE_MONITORING, DETECT_SHORTS, RETRY_CONNECTION,
            HALT, SET_VOLTAGE, SET_FREQUENCY, RUN_ALL_TESTS,
            TEST_VOLTAGE, TEST_ON_BOARD_FEEDBACK_CALIBRATION,
            TEST_SHORTS, TEST_CHANNELS, CHIP_CHECK,
            SELF_TEST_CANCEL, DETECT_DROPLETS, CHANGE_SETTINGS,
        )
        assert DropbotTopics.Requests.START_DEVICE_MONITORING == START_DEVICE_MONITORING
        assert DropbotTopics.Requests.DETECT_SHORTS == DETECT_SHORTS
        assert DropbotTopics.Requests.RETRY_CONNECTION == RETRY_CONNECTION
        assert DropbotTopics.Requests.HALT == HALT
        assert DropbotTopics.Requests.SET_VOLTAGE == SET_VOLTAGE
        assert DropbotTopics.Requests.SET_FREQUENCY == SET_FREQUENCY
        assert DropbotTopics.Requests.RUN_ALL_TESTS == RUN_ALL_TESTS
        assert DropbotTopics.Requests.TEST_VOLTAGE == TEST_VOLTAGE
        assert DropbotTopics.Requests.TEST_ON_BOARD_FEEDBACK_CALIBRATION == TEST_ON_BOARD_FEEDBACK_CALIBRATION
        assert DropbotTopics.Requests.TEST_SHORTS == TEST_SHORTS
        assert DropbotTopics.Requests.TEST_CHANNELS == TEST_CHANNELS
        assert DropbotTopics.Requests.CHIP_CHECK == CHIP_CHECK
        assert DropbotTopics.Requests.SELF_TEST_CANCEL == SELF_TEST_CANCEL
        assert DropbotTopics.Requests.DETECT_DROPLETS == DETECT_DROPLETS
        assert DropbotTopics.Requests.CHANGE_SETTINGS == CHANGE_SETTINGS

    def test_errors(self):
        from dropbot_controller.consts import DROPBOT_ERROR
        assert DropbotTopics.Errors.DROPBOT_ERROR == DROPBOT_ERROR


class TestHardwareTopicsMatchConsts:
    """Cross-check API topic values against dropbot_controller and electrode_controller consts."""

    def test_signals(self):
        from dropbot_controller.consts import (
            DROPBOT_CONNECTED, DROPBOT_DISCONNECTED,
            REALTIME_MODE_UPDATED, DISABLED_CHANNELS_CHANGED,
        )
        assert HardwareTopics.Signals.CONNECTED == DROPBOT_CONNECTED
        assert HardwareTopics.Signals.DISCONNECTED == DROPBOT_DISCONNECTED
        assert HardwareTopics.Signals.REALTIME_MODE_UPDATED == REALTIME_MODE_UPDATED
        assert HardwareTopics.Signals.DISABLED_CHANNELS_CHANGED == DISABLED_CHANNELS_CHANGED

    def test_requests(self):
        from electrode_controller.consts import ELECTRODES_STATE_CHANGE, ELECTRODES_DISABLE_REQUEST
        from dropbot_controller.consts import SET_REALTIME_MODE
        assert HardwareTopics.Requests.ELECTRODES_STATE_CHANGE == ELECTRODES_STATE_CHANGE
        assert HardwareTopics.Requests.ELECTRODES_DISABLE == ELECTRODES_DISABLE_REQUEST
        assert HardwareTopics.Requests.SET_REALTIME_MODE == SET_REALTIME_MODE


class TestUITopicsMatchConsts:
    """Cross-check API topic values against protocol_grid.consts."""

    def test_ui_topics(self):
        from protocol_grid.consts import (
            DEVICE_VIEWER_STATE_CHANGED, PROTOCOL_GRID_DISPLAY_STATE,
            CALIBRATION_DATA, DEVICE_VIEWER_SCREEN_CAPTURE,
            DEVICE_VIEWER_SCREEN_RECORDING, DEVICE_VIEWER_CAMERA_ACTIVE,
            DEVICE_VIEWER_MEDIA_CAPTURED, DEVICE_VIEWER_RECORDING_STATE,
            ROUTES_EXECUTING,
        )
        assert UITopics.DEVICE_VIEWER_STATE_CHANGED == DEVICE_VIEWER_STATE_CHANGED
        assert UITopics.PROTOCOL_GRID_DISPLAY_STATE == PROTOCOL_GRID_DISPLAY_STATE
        assert UITopics.CALIBRATION_DATA == CALIBRATION_DATA
        assert UITopics.DEVICE_VIEWER_SCREEN_CAPTURE == DEVICE_VIEWER_SCREEN_CAPTURE
        assert UITopics.DEVICE_VIEWER_SCREEN_RECORDING == DEVICE_VIEWER_SCREEN_RECORDING
        assert UITopics.DEVICE_VIEWER_CAMERA_ACTIVE == DEVICE_VIEWER_CAMERA_ACTIVE
        assert UITopics.DEVICE_VIEWER_MEDIA_CAPTURED == DEVICE_VIEWER_MEDIA_CAPTURED
        assert UITopics.DEVICE_VIEWER_RECORDING_STATE == DEVICE_VIEWER_RECORDING_STATE
        assert UITopics.ROUTES_EXECUTING == ROUTES_EXECUTING


class TestApplicationTopicsMatchConsts:

    def test_application_topics(self):
        from microdrop_application.consts import ADVANCED_MODE_CHANGE
        from protocol_grid.consts import PROTOCOL_RUNNING
        assert ApplicationTopics.ADVANCED_MODE_CHANGE == ADVANCED_MODE_CHANGE
        assert ApplicationTopics.PROTOCOL_RUNNING == PROTOCOL_RUNNING


class TestZStageTopicsMatchConsts:

    def test_signals(self):
        from peripheral_controller.consts import (
            CONNECTED, DISCONNECTED, ZSTAGE_POSITION_UPDATED,
        )
        assert ZStageTopics.Signals.CONNECTED == CONNECTED
        assert ZStageTopics.Signals.DISCONNECTED == DISCONNECTED
        assert ZStageTopics.Signals.POSITION_UPDATED == ZSTAGE_POSITION_UPDATED

    def test_requests(self):
        from peripheral_controller.consts import (
            START_DEVICE_MONITORING, GO_HOME, MOVE_UP, MOVE_DOWN,
            SET_POSITION, RETRY_CONNECTION, UPDATE_CONFIG,
        )
        assert ZStageTopics.Requests.START_DEVICE_MONITORING == START_DEVICE_MONITORING
        assert ZStageTopics.Requests.GO_HOME == GO_HOME
        assert ZStageTopics.Requests.MOVE_UP == MOVE_UP
        assert ZStageTopics.Requests.MOVE_DOWN == MOVE_DOWN
        assert ZStageTopics.Requests.SET_POSITION == SET_POSITION
        assert ZStageTopics.Requests.RETRY_CONNECTION == RETRY_CONNECTION
        assert ZStageTopics.Requests.UPDATE_CONFIG == UPDATE_CONFIG

    def test_errors(self):
        from peripheral_controller.consts import ERROR
        assert ZStageTopics.Errors.ERROR == ERROR


class TestSSHTopicsMatchConsts:

    def test_requests(self):
        from ssh_controls.consts import GENERATE_KEYPAIR, KEY_UPLOAD
        assert SSHTopics.Requests.GENERATE_KEYPAIR == GENERATE_KEYPAIR
        assert SSHTopics.Requests.KEY_UPLOAD == KEY_UPLOAD

    def test_success(self):
        from ssh_controls.consts import SSH_KEYGEN_SUCCESS, SSH_KEY_UPLOAD_SUCCESS
        assert SSHTopics.Success.SSH_KEYGEN_SUCCESS == SSH_KEYGEN_SUCCESS
        assert SSHTopics.Success.SSH_KEY_UPLOAD_SUCCESS == SSH_KEY_UPLOAD_SUCCESS

    def test_warnings(self):
        from ssh_controls.consts import SSH_KEYGEN_WARNING
        assert SSHTopics.Warnings.SSH_KEYGEN_WARNING == SSH_KEYGEN_WARNING

    def test_errors(self):
        from ssh_controls.consts import SSH_KEYGEN_ERROR, SSH_KEY_UPLOAD_ERROR
        assert SSHTopics.Errors.SSH_KEYGEN_ERROR == SSH_KEYGEN_ERROR
        assert SSHTopics.Errors.SSH_KEY_UPLOAD_ERROR == SSH_KEY_UPLOAD_ERROR

    def test_sync_experiments_request(self):
        from ssh_controls.consts import SYNC_EXPERIMENTS_REQUEST
        assert SSHTopics.Requests.SYNC_EXPERIMENTS == SYNC_EXPERIMENTS_REQUEST

    def test_sync_experiments_started(self):
        from ssh_controls.consts import SYNC_EXPERIMENTS_STARTED
        assert SSHTopics.Started.SYNC_EXPERIMENTS_STARTED == SYNC_EXPERIMENTS_STARTED

    def test_sync_experiments_success_and_error(self):
        from ssh_controls.consts import SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR
        assert SSHTopics.Success.SYNC_EXPERIMENTS_SUCCESS == SYNC_EXPERIMENTS_SUCCESS
        assert SSHTopics.Errors.SYNC_EXPERIMENTS_ERROR == SYNC_EXPERIMENTS_ERROR


class TestOpenDropTopicsMatchConsts:

    def test_signals(self):
        from opendrop_controller.consts import (
            OPENDROP_TEMPERATURES_UPDATED, OPENDROP_FEEDBACK_UPDATED,
            OPENDROP_BOARD_INFO,
        )
        assert OpenDropTopics.Signals.TEMPERATURES_UPDATED == OPENDROP_TEMPERATURES_UPDATED
        assert OpenDropTopics.Signals.FEEDBACK_UPDATED == OPENDROP_FEEDBACK_UPDATED
        assert OpenDropTopics.Signals.BOARD_INFO == OPENDROP_BOARD_INFO

    def test_requests(self):
        from opendrop_controller.consts import (
            RETRY_CONNECTION, SET_FEEDBACK, SET_TEMPERATURES,
            SET_TEMPERATURE_1, SET_TEMPERATURE_2, SET_TEMPERATURE_3,
            CHANGE_SETTINGS,
        )
        assert OpenDropTopics.Requests.RETRY_CONNECTION == RETRY_CONNECTION
        assert OpenDropTopics.Requests.SET_FEEDBACK == SET_FEEDBACK
        assert OpenDropTopics.Requests.SET_TEMPERATURES == SET_TEMPERATURES
        assert OpenDropTopics.Requests.SET_TEMPERATURE_1 == SET_TEMPERATURE_1
        assert OpenDropTopics.Requests.SET_TEMPERATURE_2 == SET_TEMPERATURE_2
        assert OpenDropTopics.Requests.SET_TEMPERATURE_3 == SET_TEMPERATURE_3
        assert OpenDropTopics.Requests.CHANGE_SETTINGS == CHANGE_SETTINGS


class TestMockDropbotTopicsMatchConsts:

    def test_requests(self):
        from mock_dropbot_controller.consts import (
            MOCK_CHANGE_SIM_SETTINGS, MOCK_SIMULATE_CONNECT,
            MOCK_SIMULATE_DISCONNECT, MOCK_SIMULATE_CHIP_INSERT,
            MOCK_SIMULATE_SHORTS, MOCK_SIMULATE_HALT,
        )
        assert MockDropbotTopics.Requests.CHANGE_SIM_SETTINGS == MOCK_CHANGE_SIM_SETTINGS
        assert MockDropbotTopics.Requests.SIMULATE_CONNECT == MOCK_SIMULATE_CONNECT
        assert MockDropbotTopics.Requests.SIMULATE_DISCONNECT == MOCK_SIMULATE_DISCONNECT
        assert MockDropbotTopics.Requests.SIMULATE_CHIP_INSERT == MOCK_SIMULATE_CHIP_INSERT
        assert MockDropbotTopics.Requests.SIMULATE_SHORTS == MOCK_SIMULATE_SHORTS
        assert MockDropbotTopics.Requests.SIMULATE_HALT == MOCK_SIMULATE_HALT

    def test_signals(self):
        from mock_dropbot_controller.consts import (
            MOCK_ACTUATED_CHANNELS_UPDATED, MOCK_STREAM_STATUS_UPDATED,
        )
        assert MockDropbotTopics.Signals.ACTUATED_CHANNELS_UPDATED == MOCK_ACTUATED_CHANNELS_UPDATED
        assert MockDropbotTopics.Signals.STREAM_STATUS_UPDATED == MOCK_STREAM_STATUS_UPDATED


class TestPGVATopicsMatchConsts:

    def test_signals(self):
        from pgva_controller_plugin.consts import (
            PGVA_CONNECTED, PGVA_DISCONNECTED, PGVA_PRESSURE_UPDATED,
            PGVA_VACUUM_UPDATED, PGVA_OUTPUT_PRESSURE_UPDATED,
            PGVA_STATUS_UPDATED, PGVA_WARNINGS_UPDATED,
            PGVA_ERRORS_UPDATED, PGVA_COMPREHENSIVE_STATUS_UPDATED,
            PGVA_HEALTH_CHECK_UPDATED, PGVA_DEVICE_INFO_UPDATED,
            PGVA_ERROR_SIGNAL,
        )
        assert PGVATopics.Signals.CONNECTED == PGVA_CONNECTED
        assert PGVATopics.Signals.DISCONNECTED == PGVA_DISCONNECTED
        assert PGVATopics.Signals.PRESSURE_UPDATED == PGVA_PRESSURE_UPDATED
        assert PGVATopics.Signals.VACUUM_UPDATED == PGVA_VACUUM_UPDATED
        assert PGVATopics.Signals.OUTPUT_PRESSURE_UPDATED == PGVA_OUTPUT_PRESSURE_UPDATED
        assert PGVATopics.Signals.STATUS_UPDATED == PGVA_STATUS_UPDATED
        assert PGVATopics.Signals.WARNINGS_UPDATED == PGVA_WARNINGS_UPDATED
        assert PGVATopics.Signals.ERRORS_UPDATED == PGVA_ERRORS_UPDATED
        assert PGVATopics.Signals.COMPREHENSIVE_STATUS_UPDATED == PGVA_COMPREHENSIVE_STATUS_UPDATED
        assert PGVATopics.Signals.HEALTH_CHECK_UPDATED == PGVA_HEALTH_CHECK_UPDATED
        assert PGVATopics.Signals.DEVICE_INFO_UPDATED == PGVA_DEVICE_INFO_UPDATED
        assert PGVATopics.Signals.ERROR == PGVA_ERROR_SIGNAL

    def test_requests(self):
        from pgva_controller_plugin.consts import (
            SET_PRESSURE, SET_VACUUM, SET_OUTPUT_PRESSURE,
            GET_PRESSURE, GET_VACUUM, GET_OUTPUT_PRESSURE,
            GET_STATUS, GET_WARNINGS, GET_ERRORS,
            GET_COMPREHENSIVE_STATUS, GET_HEALTH_CHECK, GET_DEVICE_INFO,
            ENABLE_PGVA, DISABLE_PGVA, RESET_PGVA, TRIGGER_MANUAL,
            STORE_TO_EEPROM, CONNECT_PGVA, DISCONNECT_PGVA,
        )
        assert PGVATopics.Requests.SET_PRESSURE == SET_PRESSURE
        assert PGVATopics.Requests.SET_VACUUM == SET_VACUUM
        assert PGVATopics.Requests.SET_OUTPUT_PRESSURE == SET_OUTPUT_PRESSURE
        assert PGVATopics.Requests.GET_PRESSURE == GET_PRESSURE
        assert PGVATopics.Requests.GET_VACUUM == GET_VACUUM
        assert PGVATopics.Requests.GET_OUTPUT_PRESSURE == GET_OUTPUT_PRESSURE
        assert PGVATopics.Requests.GET_STATUS == GET_STATUS
        assert PGVATopics.Requests.GET_WARNINGS == GET_WARNINGS
        assert PGVATopics.Requests.GET_ERRORS == GET_ERRORS
        assert PGVATopics.Requests.GET_COMPREHENSIVE_STATUS == GET_COMPREHENSIVE_STATUS
        assert PGVATopics.Requests.GET_HEALTH_CHECK == GET_HEALTH_CHECK
        assert PGVATopics.Requests.GET_DEVICE_INFO == GET_DEVICE_INFO
        assert PGVATopics.Requests.ENABLE == ENABLE_PGVA
        assert PGVATopics.Requests.DISABLE == DISABLE_PGVA
        assert PGVATopics.Requests.RESET == RESET_PGVA
        assert PGVATopics.Requests.TRIGGER_MANUAL == TRIGGER_MANUAL
        assert PGVATopics.Requests.STORE_TO_EEPROM == STORE_TO_EEPROM
        assert PGVATopics.Requests.CONNECT == CONNECT_PGVA
        assert PGVATopics.Requests.DISCONNECT == DISCONNECT_PGVA


# ===================================================================
# 3. get_all_topics() introspection helper
# ===================================================================

class TestGetAllTopics:

    def test_returns_dict(self):
        result = get_all_topics()
        assert isinstance(result, dict)

    def test_all_domains_present(self):
        result = get_all_topics()
        expected_domains = {
            "dropbot", "hardware", "ui", "application",
            "zstage", "ssh", "opendrop", "pgva", "mock_dropbot",
        }
        assert expected_domains == set(result.keys())

    def test_dropbot_domain_has_topics(self):
        result = get_all_topics()
        dropbot_topics = result["dropbot"]
        assert len(dropbot_topics) > 0
        # Spot-check a couple of known topics
        assert "dropbot/requests/set_voltage" in dropbot_topics
        assert "dropbot/signals/halted" in dropbot_topics

    def test_all_values_are_strings_with_slashes(self):
        result = get_all_topics()
        for domain, topics in result.items():
            for topic in topics:
                assert isinstance(topic, str), f"{domain}: {topic} is not a string"
                assert "/" in topic, f"{domain}: {topic} does not contain '/'"

    def test_topics_are_sorted(self):
        result = get_all_topics()
        for domain, topics in result.items():
            assert topics == sorted(topics), f"Topics in {domain} are not sorted"


# ===================================================================
# 4. Wildcard patterns are well-formed
# ===================================================================

class TestWildcardPatterns:

    def test_all_patterns_end_with_hash(self):
        for name in dir(WildcardPatterns):
            if name.startswith("_"):
                continue
            value = getattr(WildcardPatterns, name)
            assert value.endswith("#"), f"{name} = {value!r} does not end with '#'"

    def test_patterns_are_strings(self):
        for name in dir(WildcardPatterns):
            if name.startswith("_"):
                continue
            value = getattr(WildcardPatterns, name)
            assert isinstance(value, str)
