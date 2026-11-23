# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Sample notifications and a simulated plugin loading list for the demo."""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from traits.api import HasTraits, Instance
from traitsui.api import TableEditor, UItem, VGroup, View

# Microdrop package imports.
from notifications.consts import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_SUCCESS,
    SEVERITY_WARNING,
    NotificationSection,
    OpenPathAction,
    PublishAction,
)

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import (
    LOAD_LOADED,
    LOAD_LOADING,
    PluginLoadStatus,
)
from microdrop_utils.traitsui_qt_helpers import ObjectColumn

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
    """One entry of every kind the pane shows."""
    now = time.time()

    center.post(
        "Protocol finished",
        detail="24 steps in 6 min 12 s. The report is in the experiment folder.",
        severity=SEVERITY_SUCCESS,
        category="protocol",
        source="pluggable_protocol_tree",
        timestamp=now - 300,
        action=OpenPathAction(label="Show folder", path=str(Path.home())),
    )
    center.post(
        "Chip inserted",
        severity=SEVERITY_INFO,
        category="hardware",
        source="dropbot_controller",
        timestamp=now - 200,
    )

    for repeat in range(12):
        center.post(
            "Capacitance reading out of range on channel 42",
            severity=SEVERITY_WARNING,
            category="log",
            source="dropbot_controller.services.monitor",
            timestamp=now - 180 + repeat,
        )

    center.post(
        "Calibration is 9 days old",
        detail="Recalibrate before quantitative runs.",
        severity=SEVERITY_INFO,
        category="calibration",
        source="portable_dropbot_status_and_controls",
        timestamp=now - 120,
        action=PublishAction(label="Calibrate", topic="demo/calibrate"),
    )
    error = center.post(
        "Could not open the heater's serial port COM7",
        detail=LONG_TRACEBACK,
        severity=SEVERITY_ERROR,
        category="log",
        source="heater_controls_ui.controller",
        timestamp=now - 60,
    )
    error.expanded = True


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
