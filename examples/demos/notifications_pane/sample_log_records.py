# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Real warning and error records from past MicroDrop sessions, scrubbed of
paths, names and other machine-specific text (``log_scrubber``), for the
notifications demo. Each is replayed ``repeats`` times (the count one real
session logged it, capped), ending ``ago_s`` seconds before the demo starts.
"""

# Data: a few unbreakable tokens (a qualified class name) run past the line.
# ruff: noqa: E501

#: The records, in the order a session would log them.
SAMPLE_LOG_RECORDS = (
    {
        "ago_s": 1500,
        "repeats": 1,
        "level": "ERROR",
        "name": "dropbot_controller.services.dropbot_monitor_mixin_service",
        "message": "No device for hwids ['VID:PID=16C0:0483'] found",
        "traceback": "",
    },
    {
        "ago_s": 1490,
        "repeats": 1,
        "level": "WARNING",
        "name": "device_viewer.models.main_model",
        "message": "Failed to load calibration data from preferences: since "
        "values were not floats: liquid cap preference = None, "
        "filler capacitance preference = None",
        "traceback": "",
    },
    {
        "ago_s": 1480,
        "repeats": 1,
        "level": "WARNING",
        "name": "pluggable_protocol_tree.services.device_viewer_sync",
        "message": "failed to parse DV state: 1 validation error for "
        "DeviceViewerMessageModel\n"
        "  Invalid JSON: EOF while parsing a value at line 1 column "
        "0 [type=json_invalid, input_value=TimestampedMessage('', "
        "ti...<timestamp>), input_type=TimestampedMessage]\n"
        "    For further information visit "
        "https://errors.pydantic.dev/2.12/v/json_invalid",
        "traceback": "",
    },
    {
        "ago_s": 1200,
        "repeats": 30,
        "level": "WARNING",
        "name": "dropbot_controller.dropbot_controller_base",
        "message": "Request for electrodes_state_change denied: Dropbot is "
        "disconnected.",
        "traceback": "",
    },
    {
        "ago_s": 1100,
        "repeats": 30,
        "level": "CRITICAL",
        "name": "device_viewer.controllers.device_viewer_publish_controller",
        "message": "DEVICE VIEWER: Cannot publish electrodes state change; "
        "reasons: Realtime mode; Device Not connected;",
        "traceback": "",
    },
    {
        "ago_s": 900,
        "repeats": 697,
        "level": "WARNING",
        "name": "device_viewer.controllers.camera_controller",
        "message": "Capture setup Step 1 · Step: Gamma 120 is outside 48MP USB "
        "Camera's range (0 to 64); set to 64",
        "traceback": "",
    },
    {
        "ago_s": 880,
        "repeats": 10,
        "level": "ERROR",
        "name": "device_viewer.views.camera_control_view.qt_camera_device",
        "message": "Focus distance not read: DirectShow camera control failed: "
        "(-2147024463, 'A device which does not exist was "
        "specified.', (None, None, None, 0, None))",
        "traceback": "",
    },
    {
        "ago_s": 600,
        "repeats": 1,
        "level": "ERROR",
        "name": "traits",
        "message": "Exception occurred in traits notification handler for "
        "event object: "
        "TraitChangeEvent(object=<heater_controls_ui.plots.log_view.HeaterLogViewerController "
        "object at 0x000002759BF03BF0>, name='model', "
        "old=<heater_controls_ui.plots.log_model.HeaterLogViewerModel "
        "object at 0x000002759C25D670>, "
        "new=<heater_controls_ui.plots.log_model.HeaterLogViewerModel "
        "object at 0x000002759BF50E30>)",
        "traceback": "Traceback (most recent call last):\n"
        "  File "
        '"<env>/Lib/site-packages/traits/observation/_trait_event_notifier.py", '
        "line 122, in __call__\n"
        "    self.dispatcher(handler, event)\n"
        "    ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^\n"
        "  File "
        '"<env>/Lib/site-packages/traits/observation/observe.py", '
        "line 43, in dispatch_same\n"
        "    handler(event)\n"
        "    ~~~~~~~^^^^^^^\n"
        "  File "
        '"src/heater-microdrop-plugin-py/heater_controls_ui/plots/log_view.py", '
        "line 175, in _show_saved_log\n"
        "    saved_path = Path(event.new)\n"
        '  File "<env>/Lib/pathlib/_local.py", line 503, in '
        "__init__\n"
        "    super().__init__(*args)\n"
        "    ~~~~~~~~~~~~~~~~^^^^^^^\n"
        '  File "<env>/Lib/pathlib/_local.py", line 132, in '
        "__init__\n"
        "    raise TypeError(\n"
        "    ...<2 lines>...\n"
        '        f"not {type(path).__name__!r}")\n'
        "TypeError: argument should be a str or an os.PathLike "
        "object where __fspath__ returns a str, not "
        "'HeaterLogViewerModel'",
    },
    {
        "ago_s": 420,
        "repeats": 1,
        "level": "ERROR",
        "name": "microdrop_utils.decorators",
        "message": "On Experiment Changed failed: Internal C++ object "
        "(ExperimentLabel) already deleted.",
        "traceback": "Traceback (most recent call last):\n"
        '  File "src/microdrop_utils/decorators.py", line 41, in '
        "wrapper\n"
        "    return func(self, *args, **kwargs)\n"
        "  File "
        '"src/pluggable_protocol_tree/views/protocol_tree_pane.py", '
        "line 1036, in _on_experiment_changed\n"
        "    "
        "self.experiment_label.update_experiment_id(cur.stem)\n"
        "    "
        "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^\n"
        "  File "
        '"src/pluggable_protocol_tree/views/experiment_label.py", '
        "line 63, in update_experiment_id\n"
        "    self.setText(\n"
        "    ~~~~~~~~~~~~^\n"
        '        f"<b>Experiment: </b> "\n'
        "        ^^^^^^^^^^^^^^^^^^^^^^^\n"
        "        f\"<span style='text-decoration: underline; "
        "color: {link_color};'>\"\n"
        "        "
        "^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
        '        f"{experiment_id}</span>"\n'
        "        ^^^^^^^^^^^^^^^^^^^^^^^^^\n"
        "    )\n"
        "    ^\n"
        "RuntimeError: Internal C++ object (ExperimentLabel) "
        "already deleted.",
    },
    {
        "ago_s": 300,
        "repeats": 5,
        "level": "WARNING",
        "name": "image_viewer.analysis.imported_experiments_model",
        "message": "Plotted experiment <experiment> is missing",
        "traceback": "",
    },
    {
        "ago_s": 120,
        "repeats": 4,
        "level": "ERROR",
        "name": "microdrop_utils.dramatiq_controller_base",
        "message": "SSHControlViewModel._on_ssh_key_upload_error_triggered "
        "failed on topic ssh_service/error/ssh_key_upload_error",
        "traceback": "Traceback (most recent call last):\n"
        '  File "src/microdrop_utils/dramatiq_controller_base.py", '
        "line 273, in invoke_class_method\n"
        "    class_method(*args, **kwargs)\n"
        "    ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^\n"
        '  File "src/ssh_controls_ui/view_model.py", line 168, in '
        "_on_ssh_key_upload_error_triggered\n"
        "    message = json.loads(message)\n"
        '  File "<env>/Lib/json/__init__.py", line 352, in loads\n'
        "    return _default_decoder.decode(s)\n"
        "           ~~~~~~~~~~~~~~~~~~~~~~~^^^\n"
        '  File "<env>/Lib/json/decoder.py", line 345, in decode\n'
        "    obj, end = self.raw_decode(s, idx=_w(s, 0).end())\n"
        "               ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^\n"
        '  File "<env>/Lib/json/decoder.py", line 363, in '
        "raw_decode\n"
        '    raise JSONDecodeError("Expecting value", s, err.value) '
        "from None\n"
        "json.decoder.JSONDecodeError: Expecting value: line 1 "
        "column 1 (char 0)",
    },
)
