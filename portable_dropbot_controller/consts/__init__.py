# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Portable DropBot controller constants, topics and message contracts.

Split into topical submodules and re-exported here: sibling plugins import
# Microdrop package imports.
from this package root only (.importlinter allows ``*.consts``, not its
submodules), and submodules never import from this package root."""

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED as DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED,
)
from device_viewer.consts import (
    DEVICE_VIEWER_MEDIA_CAPTURED as DEVICE_VIEWER_MEDIA_CAPTURED,
)
from dropbot_controller.consts import DETECT_DROPLETS as DETECT_DROPLETS
from dropbot_controller.consts import (
    # The shared reply topic, re-exported for this plugin's services.
    DROPLETS_DETECTED as DROPLETS_DETECTED,
)

# Local imports.
from .board_health import HV_ENABLE_STATUS_OFF as HV_ENABLE_STATUS_OFF
from .board_health import HV_ENABLE_STATUS_ON as HV_ENABLE_STATUS_ON
from .board_health import HV_STATE_HALTED_BIT as HV_STATE_HALTED_BIT
from .board_health import AlarmRaised as AlarmRaised
from .board_health import AlarmReportEntry as AlarmReportEntry
from .board_health import FirmwareVersionsUpdated as FirmwareVersionsUpdated
from .board_health import alarm_raised_publisher as alarm_raised_publisher
from .board_health import firmware_versions_publisher as firmware_versions_publisher
from .chip import CHIP_DETECT_RULE_ANY_POGO as CHIP_DETECT_RULE_ANY_POGO
from .chip import CHIP_DETECT_RULE_BOTH_POGOS as CHIP_DETECT_RULE_BOTH_POGOS
from .chip import CHIP_DETECT_RULE_PRESENCE as CHIP_DETECT_RULE_PRESENCE
from .chip import CHIP_DETECT_RULES as CHIP_DETECT_RULES
from .chip import CHIP_ENGAGE_MODE_CLASSIC as CHIP_ENGAGE_MODE_CLASSIC
from .chip import CHIP_ENGAGE_MODE_SMART as CHIP_ENGAGE_MODE_SMART
from .chip import CHIP_ENGAGE_MODES as CHIP_ENGAGE_MODES
from .chip import CHIP_ON_PAD_POGO_BITS as CHIP_ON_PAD_POGO_BITS
from .chip import CHIP_ON_PAD_PRESENCE_BIT as CHIP_ON_PAD_PRESENCE_BIT
from .chip import CHIP_ON_PAD_SEATED_MASK as CHIP_ON_PAD_SEATED_MASK
from .chip import DEFAULT_CHIP_DETECT_RULE as DEFAULT_CHIP_DETECT_RULE
from .chip import DEFAULT_CHIP_ENGAGE_MODE as DEFAULT_CHIP_ENGAGE_MODE
from .chip import PAD_ENGAGE_ACTION_ENGAGE as PAD_ENGAGE_ACTION_ENGAGE
from .chip import PAD_ENGAGE_ACTION_RETRACT as PAD_ENGAGE_ACTION_RETRACT
from .chip import PAD_ENGAGE_CMD as PAD_ENGAGE_CMD
from .chip import PAD_ENGAGE_FAILURES as PAD_ENGAGE_FAILURES
from .chip import PAD_ENGAGE_MAX_STEPS as PAD_ENGAGE_MAX_STEPS
from .chip import PAD_ENGAGE_MODE_CLASSIC as PAD_ENGAGE_MODE_CLASSIC
from .chip import PAD_ENGAGE_MODE_SMART as PAD_ENGAGE_MODE_SMART
from .chip import PAD_ENGAGE_OVERDRIVE_UM as PAD_ENGAGE_OVERDRIVE_UM
from .chip import PAD_ENGAGE_PADS_MAY_BE_PRESSED as PAD_ENGAGE_PADS_MAY_BE_PRESSED
from .chip import PAD_ENGAGE_STATUS_MOTOR_ERROR as PAD_ENGAGE_STATUS_MOTOR_ERROR
from .chip import PAD_ENGAGE_STATUS_OK as PAD_ENGAGE_STATUS_OK
from .chip import PAD_ENGAGE_STEP_UM as PAD_ENGAGE_STEP_UM
from .chip import SMART_ENGAGE_NEEDS as SMART_ENGAGE_NEEDS
from .chip import ChipLockFailed as ChipLockFailed
from .chip import chip_lock_failed_publisher as chip_lock_failed_publisher
from .droplets import DROPLET_DETECTION_THRESHOLD_PF as DROPLET_DETECTION_THRESHOLD_PF
from .droplets import (
    DROPLET_DETECTION_THRESHOLD_PF_BOUNDS as DROPLET_DETECTION_THRESHOLD_PF_BOUNDS,
)
from .fluorescence import FILTER_NAMES as FILTER_NAMES
from .fluorescence import FILTER_POSITIONS as FILTER_POSITIONS
from .fluorescence import (
    FLUORESCENCE_AUTO_EXPOSURE_SETTLE_S as FLUORESCENCE_AUTO_EXPOSURE_SETTLE_S,
)
from .fluorescence import (
    FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S as FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S,
)
from .fluorescence import (
    FLUORESCENCE_DEFAULT_EXPOSURE_MS as FLUORESCENCE_DEFAULT_EXPOSURE_MS,
)
from .fluorescence import (
    FLUORESCENCE_DEFAULT_LED_PERCENT as FLUORESCENCE_DEFAULT_LED_PERCENT,
)
from .fluorescence import (
    FLUORESCENCE_EXPOSURE_MS_BOUNDS as FLUORESCENCE_EXPOSURE_MS_BOUNDS,
)
from .fluorescence import FLUORESCENCE_FRAME_TIMEOUT_S as FLUORESCENCE_FRAME_TIMEOUT_S
from .fluorescence import (
    FLUORESCENCE_LED_PERCENT_BOUNDS as FLUORESCENCE_LED_PERCENT_BOUNDS,
)
from .fluorescence import FLUORESCENCE_LED_RAW_MAX as FLUORESCENCE_LED_RAW_MAX
from .fluorescence import FLUORESCENCE_PARK_FILTER as FLUORESCENCE_PARK_FILTER
from .fluorescence import FLUORESCENCE_SETTLE_S as FLUORESCENCE_SETTLE_S
from .fluorescence import (
    FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S as FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S,
)
from .fluorescence import (
    FLUORESCENCE_STEP_TIMEOUT_MARGIN_S as FLUORESCENCE_STEP_TIMEOUT_MARGIN_S,
)
from .fluorescence import FLUORESCENCE_WAIT_SLICE_S as FLUORESCENCE_WAIT_SLICE_S
from .fluorescence import FluorescenceCapturedFrame as FluorescenceCapturedFrame
from .fluorescence import FluorescenceCaptureDone as FluorescenceCaptureDone
from .fluorescence import FluorescenceCaptureEntry as FluorescenceCaptureEntry
from .fluorescence import FluorescenceCaptureProgress as FluorescenceCaptureProgress
from .fluorescence import FluorescenceCaptureRequest as FluorescenceCaptureRequest
from .fluorescence import FluorescenceStepCapture as FluorescenceStepCapture
from .fluorescence import FluorescenceStepCaptureEntry as FluorescenceStepCaptureEntry
from .fluorescence import filter_label as filter_label
from .fluorescence import (
    fluorescence_capture_done_publisher as fluorescence_capture_done_publisher,
)
from .fluorescence import (
    fluorescence_capture_progress_publisher as fluorescence_capture_progress_publisher,
)
from .fluorescence import (
    fluorescence_capture_publisher as fluorescence_capture_publisher,
)
from .fluorescence import frame_description as frame_description
from .hardware import CAL_CAPS_CHOICES as CAL_CAPS_CHOICES
from .hardware import CAL_FREQUENCY as CAL_FREQUENCY
from .hardware import CAL_VOLTAGE as CAL_VOLTAGE
from .hardware import DEFAULT_BAUD_RATE as DEFAULT_BAUD_RATE
from .hardware import DEFAULT_ELECTRODE_GAIN_PERMILLE as DEFAULT_ELECTRODE_GAIN_PERMILLE
from .hardware import DEFAULT_FAN_BOARD as DEFAULT_FAN_BOARD
from .hardware import DEFAULT_FREQUENCY as DEFAULT_FREQUENCY
from .hardware import DEFAULT_LIGHT_INTENSITY as DEFAULT_LIGHT_INTENSITY
from .hardware import DEFAULT_NUM_CHANNELS as DEFAULT_NUM_CHANNELS
from .hardware import DEFAULT_VOLTAGE as DEFAULT_VOLTAGE
from .hardware import ELECTRODE_GAIN_PERMILLE_BOUNDS as ELECTRODE_GAIN_PERMILLE_BOUNDS
from .hardware import FAN_BOARDS as FAN_BOARDS
from .hardware import FIRMWARE_READ_RETRY_DELAY_S as FIRMWARE_READ_RETRY_DELAY_S
from .hardware import FREQUENCY_BOUNDS as FREQUENCY_BOUNDS
from .hardware import LIGHT_INTENSITY_BOUNDS as LIGHT_INTENSITY_BOUNDS
from .hardware import LIGHT_INTENSITY_RAW_MAX as LIGHT_INTENSITY_RAW_MAX
from .hardware import MONITOR_INTERVAL_S as MONITOR_INTERVAL_S
from .hardware import PORT_LEASE_RELEASE_DELAY_S as PORT_LEASE_RELEASE_DELAY_S
from .hardware import RGB_LIGHT_STATES as RGB_LIGHT_STATES
from .hardware import SHUTDOWN_TIMEOUT_S as SHUTDOWN_TIMEOUT_S
from .hardware import STATUS_FAILURE_DISCONNECT_LIMIT as STATUS_FAILURE_DISCONNECT_LIMIT
from .hardware import VOLTAGE_BOUNDS as VOLTAGE_BOUNDS
from .heater import DEFAULT_TEMP_CHANNEL as DEFAULT_TEMP_CHANNEL
from .heater import HEATER_FAILSAFE_ALARM_CODES as HEATER_FAILSAFE_ALARM_CODES
from .heater import TEMP_CHANNEL_MAX as TEMP_CHANNEL_MAX
from .heater import TEMP_PID_GAIN_BOUNDS as TEMP_PID_GAIN_BOUNDS
from .heater import TEMP_PID_PERIOD_MS_BOUNDS as TEMP_PID_PERIOD_MS_BOUNDS
from .heater import TEMP_REACHED_POLL_INTERVAL_S as TEMP_REACHED_POLL_INTERVAL_S
from .heater import TEMP_REACHED_TIMEOUT_S as TEMP_REACHED_TIMEOUT_S
from .heater import TEMP_TARGET_C_BOUNDS as TEMP_TARGET_C_BOUNDS
from .heater import TEMP_TARGET_MAX_MARGIN_C as TEMP_TARGET_MAX_MARGIN_C
from .heater import ProtocolSetTemperatureRequest as ProtocolSetTemperatureRequest
from .heater import TemperatureReached as TemperatureReached
from .heater import TempSetPidRequest as TempSetPidRequest
from .heater import TempSetTargetRequest as TempSetTargetRequest
from .heater import temp_set_pid_publisher as temp_set_pid_publisher
from .heater import temperature_reached_publisher as temperature_reached_publisher
from .heater_tune import (
    HEATER_TUNE_DEFAULT_DURATION_S as HEATER_TUNE_DEFAULT_DURATION_S,
)
from .heater_tune import HEATER_TUNE_DEFAULT_DUTY_PCT as HEATER_TUNE_DEFAULT_DUTY_PCT
from .heater_tune import (
    HEATER_TUNE_DEFAULT_MAX_TEMP_C as HEATER_TUNE_DEFAULT_MAX_TEMP_C,
)
from .heater_tune import HEATER_TUNE_DEFAULT_STYLE as HEATER_TUNE_DEFAULT_STYLE
from .heater_tune import HEATER_TUNE_DURATION_S_BOUNDS as HEATER_TUNE_DURATION_S_BOUNDS
from .heater_tune import HEATER_TUNE_DUTY_PCT_BOUNDS as HEATER_TUNE_DUTY_PCT_BOUNDS
from .heater_tune import HEATER_TUNE_FITTING_PHASE as HEATER_TUNE_FITTING_PHASE
from .heater_tune import HEATER_TUNE_JOIN_TIMEOUT_S as HEATER_TUNE_JOIN_TIMEOUT_S
from .heater_tune import HEATER_TUNE_MAX_TEMP_C_BOUNDS as HEATER_TUNE_MAX_TEMP_C_BOUNDS
from .heater_tune import HEATER_TUNE_OFF_ATTEMPTS as HEATER_TUNE_OFF_ATTEMPTS
from .heater_tune import HEATER_TUNE_PERIOD_MS as HEATER_TUNE_PERIOD_MS
from .heater_tune import HEATER_TUNE_SAMPLE_INTERVAL_S as HEATER_TUNE_SAMPLE_INTERVAL_S
from .heater_tune import HEATER_TUNE_STYLES as HEATER_TUNE_STYLES
from .heater_tune import HeaterTuneApplied as HeaterTuneApplied
from .heater_tune import HeaterTuneApplyRequest as HeaterTuneApplyRequest
from .heater_tune import HeaterTuneDone as HeaterTuneDone
from .heater_tune import HeaterTuneFit as HeaterTuneFit
from .heater_tune import HeaterTuneProgress as HeaterTuneProgress
from .heater_tune import HeaterTuneProposal as HeaterTuneProposal
from .heater_tune import HeaterTuneStartRequest as HeaterTuneStartRequest
from .heater_tune import heater_tune_applied_publisher as heater_tune_applied_publisher
from .heater_tune import heater_tune_apply_publisher as heater_tune_apply_publisher
from .heater_tune import heater_tune_done_publisher as heater_tune_done_publisher
from .heater_tune import (
    heater_tune_progress_publisher as heater_tune_progress_publisher,
)
from .heater_tune import heater_tune_start_publisher as heater_tune_start_publisher
from .mechanics import CHIP_CABIN_TRAY_ONLY_FLAG as CHIP_CABIN_TRAY_ONLY_FLAG
from .mechanics import CHIP_CABIN_WITH_POGOS_FLAG as CHIP_CABIN_WITH_POGOS_FLAG
from .mechanics import MAG_RESET_CMD as MAG_RESET_CMD
from .mechanics import MAGNET_DEFAULTS_FIELDS as MAGNET_DEFAULTS_FIELDS
from .mechanics import MAGNET_DEFAULTS_FORMAT as MAGNET_DEFAULTS_FORMAT
from .mechanics import MAGNET_DEFAULTS_PARAM as MAGNET_DEFAULTS_PARAM
from .mechanics import MAGNET_HEIGHT_MM_BOUNDS as MAGNET_HEIGHT_MM_BOUNDS
from .mechanics import MECHANISM_STATE_FAULT as MECHANISM_STATE_FAULT
from .mechanics import MOTOR_ESTOP_CMD as MOTOR_ESTOP_CMD
from .mechanics import MOTOR_IDS as MOTOR_IDS
from .mechanics import MOTOR_PARAM_FIELDS as MOTOR_PARAM_FIELDS
from .mechanics import MOTOR_PARAM_NAMES as MOTOR_PARAM_NAMES
from .mechanics import (
    MOTOR_SNAPSHOT_MIN_MOTOR_FIRMWARE as MOTOR_SNAPSHOT_MIN_MOTOR_FIRMWARE,
)
from .mechanics import TRAY_ACTION_CODES as TRAY_ACTION_CODES
from .mechanics import TRAY_RESET_CMD as TRAY_RESET_CMD
from .mechanics import MagnetEngageUpdated as MagnetEngageUpdated
from .mechanics import MagnetEngageWriteRequest as MagnetEngageWriteRequest
from .mechanics import MotorParamsWriteRequest as MotorParamsWriteRequest
from .mechanics import MoveTrayRequest as MoveTrayRequest
from .mechanics import (
    magnet_engage_updated_publisher as magnet_engage_updated_publisher,
)
from .mechanics import magnet_engage_write_publisher as magnet_engage_write_publisher
from .mechanics import motor_params_write_publisher as motor_params_write_publisher
from .mechanics import move_tray_publisher as move_tray_publisher
from .pmt import DEFAULT_PMT_EXPOSURE_S as DEFAULT_PMT_EXPOSURE_S
from .pmt import DEFAULT_PMT_GAIN as DEFAULT_PMT_GAIN
from .pmt import MOTOR_ACTION_PARK as MOTOR_ACTION_PARK
from .pmt import PMT_ACQUIRE_SAMPLE_RATE_HZ as PMT_ACQUIRE_SAMPLE_RATE_HZ
from .pmt import PMT_ADC_FULL_SCALE as PMT_ADC_FULL_SCALE
from .pmt import PMT_ADC_TYPES as PMT_ADC_TYPES
from .pmt import PMT_CAPTURE_LABEL_CHARS as PMT_CAPTURE_LABEL_CHARS
from .pmt import PMT_CAPTURE_LABEL_MAX_LENGTH as PMT_CAPTURE_LABEL_MAX_LENGTH
from .pmt import PMT_CAPTURE_LABEL_PATTERN as PMT_CAPTURE_LABEL_PATTERN
from .pmt import PMT_CAPTURE_SUBDIR as PMT_CAPTURE_SUBDIR
from .pmt import PMT_EXPOSURE_S_BOUNDS as PMT_EXPOSURE_S_BOUNDS
from .pmt import PMT_GAIN_BOUNDS as PMT_GAIN_BOUNDS
from .pmt import PMT_LEGACY_PARK_LOCATION as PMT_LEGACY_PARK_LOCATION
from .pmt import PMT_LOCATION_MOVING as PMT_LOCATION_MOVING
from .pmt import PMT_PRESET_PARK_MOTOR_FIRMWARE as PMT_PRESET_PARK_MOTOR_FIRMWARE
from .pmt import PMT_RF_OHMS as PMT_RF_OHMS
from .pmt import PMT_RF_OHMS_BOUNDS as PMT_RF_OHMS_BOUNDS
from .pmt import PMT_SPOT_SLOTS as PMT_SPOT_SLOTS
from .pmt import PMT_STEP_PER_SPOT_OVERHEAD_S as PMT_STEP_PER_SPOT_OVERHEAD_S
from .pmt import PMT_STEP_TIMEOUT_MARGIN_S as PMT_STEP_TIMEOUT_MARGIN_S
from .pmt import PMT_STREAM_AVG as PMT_STREAM_AVG
from .pmt import PMT_STREAM_AVG_CHOICES as PMT_STREAM_AVG_CHOICES
from .pmt import PMT_STREAM_DATA_CMD as PMT_STREAM_DATA_CMD
from .pmt import PMT_STREAM_OSR as PMT_STREAM_OSR
from .pmt import PMT_STREAM_OSR_CHOICES as PMT_STREAM_OSR_CHOICES
from .pmt import PMT_STREAM_PREEMPT_TIMEOUT_S as PMT_STREAM_PREEMPT_TIMEOUT_S
from .pmt import PMT_STREAM_PUBLISH_INTERVAL_S as PMT_STREAM_PUBLISH_INTERVAL_S
from .pmt import PMT_STREAM_WAIT_SLICE_S as PMT_STREAM_WAIT_SLICE_S
from .pmt import PMT_VREF_V as PMT_VREF_V
from .pmt import CaptureParkOption as CaptureParkOption
from .pmt import PmtAcquireDone as PmtAcquireDone
from .pmt import PmtAcquireRequest as PmtAcquireRequest
from .pmt import PmtAdcUpdated as PmtAdcUpdated
from .pmt import PmtCaptureDone as PmtCaptureDone
from .pmt import PmtCaptureEntry as PmtCaptureEntry
from .pmt import PmtCaptureProgress as PmtCaptureProgress
from .pmt import PmtCaptureRequest as PmtCaptureRequest
from .pmt import PmtSpot as PmtSpot
from .pmt import PmtSpotResult as PmtSpotResult
from .pmt import PmtSpotsUpdated as PmtSpotsUpdated
from .pmt import PmtStepCapture as PmtStepCapture
from .pmt import PmtStepCaptureEntry as PmtStepCaptureEntry
from .pmt import PmtStreamRequest as PmtStreamRequest
from .pmt import PmtStreamSettings as PmtStreamSettings
from .pmt import PmtStreamUpdated as PmtStreamUpdated
from .pmt import pmt_acquire_done_publisher as pmt_acquire_done_publisher
from .pmt import pmt_acquire_publisher as pmt_acquire_publisher
from .pmt import pmt_adc_updated_publisher as pmt_adc_updated_publisher
from .pmt import pmt_capture_done_publisher as pmt_capture_done_publisher
from .pmt import pmt_capture_progress_publisher as pmt_capture_progress_publisher
from .pmt import pmt_capture_publisher as pmt_capture_publisher
from .pmt import pmt_spots_updated_publisher as pmt_spots_updated_publisher
from .pmt import pmt_stream_start_publisher as pmt_stream_start_publisher
from .pmt import pmt_stream_updated_publisher as pmt_stream_updated_publisher
from .settings import APP_GLOBALS_KEYS as APP_GLOBALS_KEYS
from .settings import BAUD_RATE_KEY as BAUD_RATE_KEY
from .settings import CHIP_DETECT_RULE_KEY as CHIP_DETECT_RULE_KEY
from .settings import CHIP_ENGAGE_MODE_KEY as CHIP_ENGAGE_MODE_KEY
from .settings import DEFAULT_FREQUENCY_KEY as DEFAULT_FREQUENCY_KEY
from .settings import DEFAULT_LIGHT_INTENSITY_KEY as DEFAULT_LIGHT_INTENSITY_KEY
from .settings import DEFAULT_VOLTAGE_KEY as DEFAULT_VOLTAGE_KEY
from .settings import (
    DROPLET_DETECTION_THRESHOLD_PF_KEY as DROPLET_DETECTION_THRESHOLD_PF_KEY,
)
from .settings import FAN_BOARD_KEY as FAN_BOARD_KEY
from .settings import (
    LAST_CHANNEL_STATES_REQUESTED_KEY as LAST_CHANNEL_STATES_REQUESTED_KEY,
)
from .settings import PORT_HINT_KEY as PORT_HINT_KEY
from .settings import (
    PORTABLE_DROPBOT_PREFERENCES_APP_GLOBALS_KEYS as PORTABLE_DROPBOT_PREFERENCES_APP_GLOBALS_KEYS,  # noqa: E501
)
from .settings import (
    PORTABLE_DROPBOT_PREFERENCES_PATH as PORTABLE_DROPBOT_PREFERENCES_PATH,
)
from .topics import ALARM_RAISED as ALARM_RAISED
from .topics import CALIBRATION_UPDATED as CALIBRATION_UPDATED
from .topics import CHIP_LOCK_FAILED as CHIP_LOCK_FAILED
from .topics import CLEAR_HALT as CLEAR_HALT
from .topics import CONNECT_TO_PORT as CONNECT_TO_PORT
from .topics import DISCONNECT as DISCONNECT
from .topics import ELECTRODES_STATE_CHANGE as ELECTRODES_STATE_CHANGE
from .topics import ERROR_RAISED as ERROR_RAISED
from .topics import FIRMWARE_VERSIONS_UPDATED as FIRMWARE_VERSIONS_UPDATED
from .topics import FLUORESCENCE_CAPTURE as FLUORESCENCE_CAPTURE
from .topics import FLUORESCENCE_CAPTURE_ABORT as FLUORESCENCE_CAPTURE_ABORT
from .topics import FLUORESCENCE_CAPTURE_DONE as FLUORESCENCE_CAPTURE_DONE
from .topics import FLUORESCENCE_CAPTURE_PROGRESS as FLUORESCENCE_CAPTURE_PROGRESS
from .topics import HEATER_TUNE_APPLIED as HEATER_TUNE_APPLIED
from .topics import HEATER_TUNE_APPLY as HEATER_TUNE_APPLY
from .topics import HEATER_TUNE_CANCEL as HEATER_TUNE_CANCEL
from .topics import HEATER_TUNE_DONE as HEATER_TUNE_DONE
from .topics import HEATER_TUNE_PROGRESS as HEATER_TUNE_PROGRESS
from .topics import HEATER_TUNE_START as HEATER_TUNE_START
from .topics import HOME_ALL as HOME_ALL
from .topics import LOCK_CHIP as LOCK_CHIP
from .topics import MAGNET_APPLIED as MAGNET_APPLIED
from .topics import MAGNET_ENGAGE_PRESET as MAGNET_ENGAGE_PRESET
from .topics import MAGNET_ENGAGE_READ as MAGNET_ENGAGE_READ
from .topics import MAGNET_ENGAGE_UPDATED as MAGNET_ENGAGE_UPDATED
from .topics import MAGNET_ENGAGE_WRITE as MAGNET_ENGAGE_WRITE
from .topics import MOTOR_ESTOP as MOTOR_ESTOP
from .topics import MOTOR_HOME as MOTOR_HOME
from .topics import MOTOR_MOVE as MOTOR_MOVE
from .topics import MOTOR_PARAMS_PRESET as MOTOR_PARAMS_PRESET
from .topics import MOTOR_PARAMS_READ as MOTOR_PARAMS_READ
from .topics import MOTOR_PARAMS_UPDATED as MOTOR_PARAMS_UPDATED
from .topics import MOTOR_PARAMS_WRITE as MOTOR_PARAMS_WRITE
from .topics import MOTOR_SET_SPEED as MOTOR_SET_SPEED
from .topics import MOTOR_STOP as MOTOR_STOP
from .topics import MOTORS_UPDATED as MOTORS_UPDATED
from .topics import MOVE_MAGNET as MOVE_MAGNET
from .topics import MOVE_TRAY as MOVE_TRAY
from .topics import PMT_ACQUIRE as PMT_ACQUIRE
from .topics import PMT_ACQUIRE_DONE as PMT_ACQUIRE_DONE
from .topics import PMT_ADC_QUERY as PMT_ADC_QUERY
from .topics import PMT_ADC_UPDATED as PMT_ADC_UPDATED
from .topics import PMT_CAPTURE as PMT_CAPTURE
from .topics import PMT_CAPTURE_ABORT as PMT_CAPTURE_ABORT
from .topics import PMT_CAPTURE_DONE as PMT_CAPTURE_DONE
from .topics import PMT_CAPTURE_PROGRESS as PMT_CAPTURE_PROGRESS
from .topics import PMT_MOVE_TO_SPOT as PMT_MOVE_TO_SPOT
from .topics import PMT_POWER as PMT_POWER
from .topics import PMT_SET_GAIN as PMT_SET_GAIN
from .topics import PMT_SPOTS_READ as PMT_SPOTS_READ
from .topics import PMT_SPOTS_UPDATED as PMT_SPOTS_UPDATED
from .topics import PMT_STREAM_START as PMT_STREAM_START
from .topics import PMT_STREAM_STOP as PMT_STREAM_STOP
from .topics import PMT_STREAM_UPDATED as PMT_STREAM_UPDATED
from .topics import PMT_UPDATED as PMT_UPDATED
from .topics import PORTABLE_DROPBOT_CONNECTED as PORTABLE_DROPBOT_CONNECTED
from .topics import PORTABLE_DROPBOT_DISCONNECTED as PORTABLE_DROPBOT_DISCONNECTED
from .topics import PORTS_UPDATED as PORTS_UPDATED
from .topics import PROTOCOL_SET_MAGNET as PROTOCOL_SET_MAGNET
from .topics import PROTOCOL_SET_TEMPERATURE as PROTOCOL_SET_TEMPERATURE
from .topics import READ_CAL_CAPS as READ_CAL_CAPS
from .topics import READ_ELECTRODE_GAIN as READ_ELECTRODE_GAIN
from .topics import REALTIME_MODE_UPDATED as REALTIME_MODE_UPDATED
from .topics import REBOOT_MOTOR_BOARD as REBOOT_MOTOR_BOARD
from .topics import REFRESH_MOTORS as REFRESH_MOTORS
from .topics import REFRESH_PORTS as REFRESH_PORTS
from .topics import RETRY_CONNECTION as RETRY_CONNECTION
from .topics import RUN_CAP_CALIBRATION as RUN_CAP_CALIBRATION
from .topics import SET_BUZZER as SET_BUZZER
from .topics import SET_CAL_CAPS as SET_CAL_CAPS
from .topics import SET_ELECTRODE_GAIN as SET_ELECTRODE_GAIN
from .topics import SET_FAN as SET_FAN
from .topics import SET_FILTER as SET_FILTER
from .topics import SET_FLUORESCENCE_LED_RAW as SET_FLUORESCENCE_LED_RAW
from .topics import SET_FREQUENCY as SET_FREQUENCY
from .topics import SET_ILLUMINATION_RAW as SET_ILLUMINATION_RAW
from .topics import SET_LIGHT_INTENSITY as SET_LIGHT_INTENSITY
from .topics import SET_LIGHT_ON as SET_LIGHT_ON
from .topics import SET_ML_REALTIME as SET_ML_REALTIME
from .topics import SET_POGO as SET_POGO
from .topics import SET_REALTIME_MODE as SET_REALTIME_MODE
from .topics import SET_RGB_LIGHT as SET_RGB_LIGHT
from .topics import SET_VOLTAGE as SET_VOLTAGE
from .topics import STATUS_UPDATED as STATUS_UPDATED
from .topics import TEMP_CONTROL as TEMP_CONTROL
from .topics import TEMP_READ_INFO as TEMP_READ_INFO
from .topics import TEMP_READ_PID as TEMP_READ_PID
from .topics import TEMP_SET_PID as TEMP_SET_PID
from .topics import TEMP_SET_TARGET as TEMP_SET_TARGET
from .topics import TEMP_UPDATED as TEMP_UPDATED
from .topics import TEMPERATURE_REACHED as TEMPERATURE_REACHED

# The plugin package: this consts package's parent.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics the actor declared by this plugin subscribes to. The two device
# viewer signals are the camera's replies to the fluorescence capture
# routine; the listener dispatches them to on_<last segment>_signal.
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "portable_dropbot/requests/#",
        "hardware/requests/#",
        # Find liquid and the droplet-check columns use the DropBot's topic.
        DETECT_DROPLETS,
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
        # A heater failsafe alarm fails a waiting protocol temperature step.
        ALARM_RAISED,
        DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED,
        DEVICE_VIEWER_MEDIA_CAPTURED,
    ]
}
