# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Every topic this plugin publishes or handles."""

# Shared hardware topics (same strings every device backend uses; the
# backend with a live proxy is the one that acts).
PORTABLE_DROPBOT_CONNECTED = "hardware/signals/connected"
PORTABLE_DROPBOT_DISCONNECTED = "hardware/signals/disconnected"
ELECTRODES_STATE_CHANGE = "hardware/requests/electrodes_state_change"
SET_REALTIME_MODE = "hardware/requests/set_realtime_mode"
REALTIME_MODE_UPDATED = "hardware/signals/realtime_mode_updated"

# Signals published by this plugin.
STATUS_UPDATED = "portable_dropbot/signals/status_updated"
#: Serial ports present on the machine that owns the hardware — the
#: frontend can be remote, so the backend enumerates and publishes.
PORTS_UPDATED = "portable_dropbot/signals/ports_updated"
MOTORS_UPDATED = "portable_dropbot/signals/motors_updated"
#: Calibration pane feedback: macro stage progress, gain/cal-caps
#: readbacks, ML-path state.
CALIBRATION_UPDATED = "portable_dropbot/signals/calibration_updated"
#: Temp pane feedback: per-channel readings and PID readbacks.
TEMP_UPDATED = "portable_dropbot/signals/temp_updated"
#: Heater auto-tune feedback: each reading of a running step capture or
#: verify run (HeaterTuneProgress), the fit and proposed gains or the
#: refusal (HeaterTuneDone), an apply's outcome (HeaterTuneApplied), and a
#: verify run's response metrics or refusal (HeaterTuneVerifyDone).
HEATER_TUNE_PROGRESS = "portable_dropbot/signals/heater_tune_progress"
HEATER_TUNE_DONE = "portable_dropbot/signals/heater_tune_done"
HEATER_TUNE_APPLIED = "portable_dropbot/signals/heater_tune_applied"
HEATER_TUNE_VERIFY_DONE = "portable_dropbot/signals/heater_tune_verify_done"
#: PMT pane feedback: power state, gain, acquire results.
PMT_UPDATED = "portable_dropbot/signals/pmt_updated"
#: PMT Capture pane: the board's configured spots (PmtSpotsUpdated), per-spot
#: progress of a running capture (PmtCaptureProgress), and the outcome
#: (PmtCaptureDone).
PMT_SPOTS_UPDATED = "portable_dropbot/signals/pmt_spots_updated"
PMT_CAPTURE_PROGRESS = "portable_dropbot/signals/pmt_capture_progress"
PMT_CAPTURE_DONE = "portable_dropbot/signals/pmt_capture_done"
#: Live stream state plus each batch of samples (PmtStreamUpdated).
PMT_STREAM_UPDATED = "portable_dropbot/signals/pmt_stream_updated"
#: The signal board's detected PMT ADC (PmtAdcUpdated).
PMT_ADC_UPDATED = "portable_dropbot/signals/pmt_adc_updated"
#: Outcome of a buffered acquire saved to CSV (PmtAcquireDone).
PMT_ACQUIRE_DONE = "portable_dropbot/signals/pmt_acquire_done"
#: Fluorescence Capture pane and column: per-stage progress of a running
#: capture (FluorescenceCaptureProgress) and its outcome
#: (FluorescenceCaptureDone).
FLUORESCENCE_CAPTURE_PROGRESS = "portable_dropbot/signals/fluorescence_capture_progress"
FLUORESCENCE_CAPTURE_DONE = "portable_dropbot/signals/fluorescence_capture_done"
#: Motor-params pane feedback: read-back field values (with the blob size
#: the board served and its speed units), write/preset/reboot outcomes.
MOTOR_PARAMS_UPDATED = "portable_dropbot/signals/motor_params_updated"
#: Magnet engage height feedback (MagnetEngageUpdated): the read-back
#: value and write/preset outcomes, for the preferences tab.
MAGNET_ENGAGE_UPDATED = "portable_dropbot/signals/magnet_engage_updated"
#: Protocol-step acks: the magnet move finished / the heater channel
#: reading is within the step's tolerance of its target, or the step
#: failed (TemperatureReached.error: a refused setpoint, a failsafe alarm).
MAGNET_APPLIED = "portable_dropbot/signals/magnet_applied"
TEMPERATURE_REACHED = "portable_dropbot/signals/temperature_reached"
#: Driver alarm pushes (AlarmRaised): raises AND clears, one report each.
ALARM_RAISED = "portable_dropbot/signals/alarm"
ERROR_RAISED = "portable_dropbot/signals/error"
#: A smart chip lock or a pad retract that did not finish (ChipLockFailed).
CHIP_LOCK_FAILED = "portable_dropbot/signals/chip_lock_failed"
#: The boards' firmware versions, read once per connect
#: (FirmwareVersionsUpdated).
FIRMWARE_VERSIONS_UPDATED = "portable_dropbot/signals/firmware_versions_updated"

# Request topics handled by this plugin.
RETRY_CONNECTION = "portable_dropbot/requests/retry_connection"
#: Explicit user-chosen serial port (e.g. COM5) to connect on, from
#: the status pane's port picker; empty message = resume scanning.
CONNECT_TO_PORT = "portable_dropbot/requests/connect_to_port"
#: Ask the backend to publish its current port list (PORTS_UPDATED).
REFRESH_PORTS = "portable_dropbot/requests/refresh_ports"
#: User-requested disconnect; pauses the port scanner so the board
#: is not immediately re-acquired.
DISCONNECT = "portable_dropbot/requests/disconnect"
#: Clear a latched firmware halt (HALT_CLEAR); empty message. HV stays off
#: until realtime mode enables it again.
CLEAR_HALT = "portable_dropbot/requests/clear_halt"
SET_VOLTAGE = "portable_dropbot/requests/set_voltage"
SET_FREQUENCY = "portable_dropbot/requests/set_frequency"
#: Move the chip tray (MoveTrayRequest). A legacy bare "in"/"out"/"toggle"
#: string is still accepted and runs the pogo pushpad macro.
MOVE_TRAY = "portable_dropbot/requests/move_tray"
MOVE_MAGNET = "portable_dropbot/requests/move_magnet"
#: Protocol-step magnet: JSON {"on": bool, "height_mm": float}; acks
#: on MAGNET_APPLIED once the move has finished.
PROTOCOL_SET_MAGNET = "portable_dropbot/requests/protocol_set_magnet"
SET_FILTER = "portable_dropbot/requests/set_filter"
SET_POGO = "portable_dropbot/requests/set_pogo"
#: Chip lock IS the pogo pads pressing the chip; its own topic so
#: protocol steps and panes can say what they mean.
LOCK_CHIP = "portable_dropbot/requests/lock_chip"
SET_LIGHT_INTENSITY = "portable_dropbot/requests/set_light_intensity"
#: Illumination on/off without losing the % setpoint.
SET_LIGHT_ON = "portable_dropbot/requests/set_light_on"
SET_RGB_LIGHT = "portable_dropbot/requests/set_rgb_light"
#: Raw firmware-unit variants, mirroring the vendor UI's
#: Temp/Lighting tab (illumination 0-255, fluorescence 0-65535).
SET_ILLUMINATION_RAW = "portable_dropbot/requests/set_illumination_raw"
SET_FLUORESCENCE_LED_RAW = "portable_dropbot/requests/set_fluorescence_led_raw"
# Calibration (see the calibration mixin service).
RUN_CAP_CALIBRATION = "portable_dropbot/requests/run_cap_calibration"
SET_ML_REALTIME = "portable_dropbot/requests/set_ml_realtime"
SET_ELECTRODE_GAIN = "portable_dropbot/requests/set_electrode_gain"
READ_ELECTRODE_GAIN = "portable_dropbot/requests/read_electrode_gain"
SET_CAL_CAPS = "portable_dropbot/requests/set_cal_caps"
READ_CAL_CAPS = "portable_dropbot/requests/read_cal_caps"
# Heater temperature control (per channel).
TEMP_SET_TARGET = "portable_dropbot/requests/temp_set_target"
TEMP_CONTROL = "portable_dropbot/requests/temp_control"
TEMP_READ_INFO = "portable_dropbot/requests/temp_read_info"
TEMP_READ_PID = "portable_dropbot/requests/temp_read_pid"
TEMP_SET_PID = "portable_dropbot/requests/temp_set_pid"
#: Protocol-step heater: JSON {"channel": int, "target_c": float,
#: "tolerance_c": float}; sets the target, turns control on and acks
#: on TEMPERATURE_REACHED once the reading is within tolerance.
PROTOCOL_SET_TEMPERATURE = "portable_dropbot/requests/protocol_set_temperature"
#: Heater auto-tune: start a step capture (HeaterTuneStartRequest), cancel
#: it or a verify run (raw publish_message, empty message, like
#: PMT_CAPTURE_ABORT; the heater is switched off), write a proposal
#: (HeaterTuneApplyRequest), and verify the gains on the board with a
#: regulated run to a set point (HeaterTuneVerifyStartRequest).
HEATER_TUNE_START = "portable_dropbot/requests/heater_tune_start"
HEATER_TUNE_CANCEL = "portable_dropbot/requests/heater_tune_cancel"
HEATER_TUNE_APPLY = "portable_dropbot/requests/heater_tune_apply"
HEATER_TUNE_VERIFY_START = "portable_dropbot/requests/heater_tune_verify_start"
# PMT.
PMT_POWER = "portable_dropbot/requests/pmt_power"
PMT_SET_GAIN = "portable_dropbot/requests/pmt_set_gain"
#: Buffered acquire (PmtAcquireRequest), collected and saved to CSV.
PMT_ACQUIRE = "portable_dropbot/requests/pmt_acquire"
#: Start a live stream (PmtStreamRequest); sent again while streaming it is
#: a live avg/osr/gain update, with no restart or sample gap.
PMT_STREAM_START = "portable_dropbot/requests/pmt_stream_start"
PMT_STREAM_STOP = "portable_dropbot/requests/pmt_stream_stop"
#: Query the PMT ADC type; answers on PMT_ADC_UPDATED.
PMT_ADC_QUERY = "portable_dropbot/requests/pmt_adc_query"
#: Re-read the motor board's PMT position table and publish PMT_SPOTS_UPDATED.
PMT_SPOTS_READ = "portable_dropbot/requests/pmt_spots_read"
#: Move the PMT to spot 0..PMT_SPOT_SLOTS (0 = park, where homing ends; the
#: last spot needs PMT_PRESET_PARK_MOTOR_FIRMWARE); payload is the spot
#: number as text. Refused while a PMT capture runs.
PMT_MOVE_TO_SPOT = "portable_dropbot/requests/pmt_move_to_spot"
#: Run the multi-spot capture routine (PmtCaptureRequest); one CSV per spot.
PMT_CAPTURE = "portable_dropbot/requests/pmt_capture"
#: Stop the running capture after the current spot's teardown.
PMT_CAPTURE_ABORT = "portable_dropbot/requests/pmt_capture_abort"
#: Run the fluorescence capture routine (FluorescenceCaptureRequest): per
#: entry, filter wheel -> LED -> camera controls -> one saved frame.
FLUORESCENCE_CAPTURE = "portable_dropbot/requests/fluorescence_capture"
#: Stop the running fluorescence capture; its teardown still runs. Raw
#: publish_message with an empty message, exactly like PMT_CAPTURE_ABORT.
FLUORESCENCE_CAPTURE_ABORT = "portable_dropbot/requests/fluorescence_capture_abort"
# Power system (advanced): fan and buzzer only.
#: JSON {"on": bool, "board"?: one of FAN_BOARDS}; board is optional and
#: defaults to the fan-board preference (PortableDropbotPreferences.fan_board).
SET_FAN = "portable_dropbot/requests/set_fan"
SET_BUZZER = "portable_dropbot/requests/set_buzzer"
# Motor mechanical params (advanced): read, RAM write (MotorParamsWrite,
# live on the motor's next idle moment), flash preset, and the motor-board
# reboot (it re-runs boot homing; motor commands answer BUSY meanwhile).
MOTOR_PARAMS_READ = "portable_dropbot/requests/motor_params_read"
MOTOR_PARAMS_WRITE = "portable_dropbot/requests/motor_params_write"
MOTOR_PARAMS_PRESET = "portable_dropbot/requests/motor_params_preset"
REBOOT_MOTOR_BOARD = "portable_dropbot/requests/reboot_motor_board"
#: Magnet engage height in the motor board's device defaults: read it, write
#: it to RAM (MagnetEngageWriteRequest), or preset RAM to flash. Read and
#: preset take an empty message.
MAGNET_ENGAGE_READ = "portable_dropbot/requests/magnet_engage_read"
MAGNET_ENGAGE_WRITE = "portable_dropbot/requests/magnet_engage_write"
MAGNET_ENGAGE_PRESET = "portable_dropbot/requests/magnet_engage_preset"
#: Run the vendor UI's Home All host plan (HV off first); empty message.
HOME_ALL = "portable_dropbot/requests/home_all"
#: EMERGENCY STOP — MOTORS (MOTOR_ESTOP), the vendor UI's E-STOP: every axis
#: ramps down at once and any move, home or Home All in flight is aborted.
#: Motors only: HV, the PMT supply, heaters and the rails are untouched.
#: Raw publish_message with an empty message, like PMT_CAPTURE_ABORT.
MOTOR_ESTOP = "portable_dropbot/requests/motor_estop"
MOTOR_MOVE = "portable_dropbot/requests/motor_move"
MOTOR_SET_SPEED = "portable_dropbot/requests/motor_set_speed"
MOTOR_STOP = "portable_dropbot/requests/motor_stop"
MOTOR_HOME = "portable_dropbot/requests/motor_home"
REFRESH_MOTORS = "portable_dropbot/requests/refresh_motors"
