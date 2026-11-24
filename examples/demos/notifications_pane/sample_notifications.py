# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Sample notifications and a simulated plugin loading list for the demo.

The log entries are real records from past sessions (scrubbed, in
``sample_log_records``), sent through the app's own log handler; the
protocol and calibration ones stand in for what plugins post on the topic.
"""

# Standard library imports.
import logging
import time
from pathlib import Path

# Enthought library imports.
from traits.api import HasTraits, Instance
from traitsui.api import TableEditor, UItem, VGroup, View

# Microdrop package imports.
from notifications.consts import (
    SEVERITY_INFO,
    SEVERITY_SUCCESS,
    NotificationSection,
    OpenPathAction,
    PublishAction,
)
from notifications.services.log_forwarder import NotificationLogHandler

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import (
    LOAD_LOADED,
    LOAD_LOADING,
    PluginLoadStatus,
)
from microdrop_utils.traitsui_qt_helpers import ObjectColumn

# Local imports.
from .log_records import LoggedRecord, log_record
from .sample_log_records import SAMPLE_LOG_RECORDS

#: Seconds over which a sample's repeats are spread, before its time.
REPEAT_SPREAD_S = 60

#: The simulated plugins, in load order; the one marked True fails.
DEMO_PLUGINS = [
    ("microdrop_application.plugin", "Microdrop Plugin", False),
    ("device_viewer.plugin", "Device Viewer Plugin", False),
    ("pluggable_protocol_tree.plugin", "Protocol Tree Plugin", False),
    ("heater_controls_ui.plugin", "Heater Controls UI Plugin", True),
    ("image_viewer.plugin", "Image Viewer Plugin", False),
    ("user_help_plugin.plugin", "User Help Plugin", False),
]

LONG_TRACEBACK = """Traceback (most recent call last):
  File "microdrop_utils/isolating_plugin_manager.py", line 158, in start_isolated
    self.start_plugin(plugin)
  File "envisage/plugin_manager.py", line 220, in start_plugin
    plugin.start()
  File "heater_controls_ui/plugin.py", line 88, in start
    self._controller = HeaterController(port=self.preferences.port)
  File "heater_controls_ui/controller.py", line 41, in __init__
    self._serial = serial.Serial(port, baudrate=115200, timeout=0.5)
  File "serial/serialwin32.py", line 64, in open
    raise SerialException(f"could not open port {self.name!r}: {msg!r}")
serial.serialutil.SerialException: could not open port 'COM7': \
FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"""


def post_samples(center):
    """Real logged warnings and errors, through the app's own log handler,
    and two notifications of the kind plugins post on the topic."""
    now = time.time()

    post_log_samples(center, now)

    center.post(
        "Protocol finished",
        detail="24 steps in 6 min 12 s. The report is in the experiment folder.",
        severity=SEVERITY_SUCCESS,
        category="protocol",
        source="pluggable_protocol_tree",
        timestamp=now - 240,
        action=OpenPathAction(label="Show folder", path=str(Path.home())),
    )
    center.post(
        "Calibration is 9 days old",
        detail="Recalibrate before quantitative runs.",
        severity=SEVERITY_INFO,
        category="calibration",
        source="portable_dropbot_status_and_controls",
        timestamp=now - 60,
        action=PublishAction(label="Calibrate", topic="demo/calibrate"),
    )


def post_log_samples(center, now):
    """SAMPLE_LOG_RECORDS through a NotificationLogHandler, so their titles,
    details and counts are exactly what the app would show."""
    handler = NotificationLogHandler(center, invoke_after=lambda delay, call: call())

    for sample in SAMPLE_LOG_RECORDS:
        logged = LoggedRecord(
            created=0.0,
            levelno=logging.getLevelName(sample["level"]),
            name=sample["name"],
            message=sample["message"],
            traceback=sample["traceback"],
        )
        repeats = sample["repeats"]

        # Repeats spread over the minute before their time.
        for repeat in range(repeats):
            created = now - sample["ago_s"] - REPEAT_SPREAD_S * (1 - repeat / repeats)
            handler.handle(log_record(logged, created=created))


class _LoadListView(HasTraits):
    """The simulated plugin loading list."""

    status = Instance(PluginLoadStatus)

    traits_view = View(
        VGroup(
            UItem("object.status.summary", style="readonly"),
            UItem(
                "object.status.records",
                editor=TableEditor(
                    columns=[
                        ObjectColumn(name="state", label="", editable=False),
                        ObjectColumn(name="name", label="Plugin", editable=False),
                        ObjectColumn(name="error", label="Error", editable=False),
                    ],
                    editable=False,
                    sortable=False,
                    auto_size=True,
                ),
            ),
        )
    )


def plugin_loading_section(status):
    """A section like the one plugin_management contributes, over ``status``."""

    def build(parent):
        return _LoadListView(status=status).edit_traits(kind="subpanel", parent=parent)

    return NotificationSection(
        id="demo.plugins", title="Plugins", summary=status.summary, factory=build
    )


def load_next_plugin(status, section):
    """Advance the simulated loading by one step; False once all are in."""

    for plugin_id, name, fails in DEMO_PLUGINS:
        record = status.get_record(plugin_id)

        if record is None:
            status.mark_pending(plugin_id, name).state = LOAD_LOADING
            section.summary = status.summary

            return True

        if record.state == LOAD_LOADING:
            if fails:
                status.mark_failed(plugin_id, "SerialException: COM7", LONG_TRACEBACK)

            else:
                record.trait_set(state=LOAD_LOADED, duration=0.12)

            section.summary = status.summary

            return True

    return False
