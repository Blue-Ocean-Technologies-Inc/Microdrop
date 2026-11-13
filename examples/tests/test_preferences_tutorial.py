# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Preferences tutorial's settings finder against the preference classes.

Each finder row names its preferences node and key; rows with a
``data-default`` also state the fresh-install value. These tests fail when a
setting is renamed or moved, or its default changes in code but not on the
page. Only class-level declarations and default methods are read: no helper
is instantiated, so no preferences file or Redis server is touched.
"""

# Standard library imports.
import json
import os
from html.parser import HTMLParser

# Qt reads the platform when the first QApplication is made, which importing
# the plugins below can do; set it first so no test ever opens a window.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Enthought library imports.
from pyface.qt import QtGui

# Microdrop package imports.
from device_viewer.preferences import (
    DeviceViewerAdvancedPreferences,
    DeviceViewerPreferences,
)
from device_viewer.views.camera_control_view.preferences import CameraPreferences
from dropbot_controller.preferences import DropbotPreferences
from dropbot_preferences_ui.models import VoltageFrequencyRangePreferences
from dropbot_status_and_controls.preferences import (
    DropbotStatusAndControlsPreferences,
)
from image_viewer.preferences import ImageViewerPreferences
from microdrop_application.consts import PREFERENCES_TUTORIAL_HTML_PATH
from microdrop_application.preferences import MicrodropPreferences
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from portable_dropbot_status_and_controls.preferences import (
    PortableDropbotSettingsPreferences,
)
from ssh_controls_ui.preferences import SSHControlPreferences

# Logger import.
from logger.preferences import LoggerPreferences

SOURCE_PATH = PREFERENCES_TUTORIAL_HTML_PATH.with_name("preferences.src.html")

#: Every preferences helper behind a Preferences tab in this repo.
HELPERS = (
    MicrodropPreferences,
    LoggerPreferences,
    DeviceViewerPreferences,
    DeviceViewerAdvancedPreferences,
    CameraPreferences,
    ProtocolPreferences,
    VoltageFrequencyRangePreferences,
    DropbotPreferences,
    DropbotStatusAndControlsPreferences,
    ImageViewerPreferences,
    SSHControlPreferences,
    PortableDropbotSettingsPreferences,
)


class _FinderRows(HTMLParser):
    """Collect the ``(node, key, default)`` of every finder row naming a key;
    ``default`` is None when the row states no checkable default."""

    def __init__(self):
        super().__init__()
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "tr" and "data-key" in attrs:
            self.rows.append(
                (attrs["data-node"], attrs["data-key"], attrs.get("data-default"))
            )


def _finder_rows():
    parser = _FinderRows()
    parser.feed(SOURCE_PATH.read_text(encoding="utf-8"))

    return parser.rows


def _helpers_by_node():
    # A plain-string preferences_path override shows only in __class_traits__.
    return {
        helper.__class_traits__["preferences_path"].default: helper
        for helper in HELPERS
    }


def _code_default(helper, key):
    """The fresh-install value: the default method's, else the declared one."""
    default_method = getattr(helper, f"_{key}_default", None)

    if default_method is not None:
        # The checked default methods return a constant and ignore self.
        value = default_method(None)

    else:
        value = helper.class_traits()[key].default

    if isinstance(value, QtGui.QColor):
        value = value.name()

    return value


def test_every_finder_row_names_a_real_setting():
    helpers = _helpers_by_node()
    rows = _finder_rows()

    assert len(rows) > 60

    for node, key, _default in rows:
        assert node in helpers, f"no preferences helper for node {node!r}"
        assert key in helpers[node].class_traits(), f"{node}.{key} is not in code"


def test_finder_defaults_match_the_code():
    helpers = _helpers_by_node()
    checked = [row for row in _finder_rows() if row[2] is not None]

    assert len(checked) > 50

    for node, key, page_default in checked:
        assert _code_default(helpers[node], key) == json.loads(page_default), (
            f"{node}.{key}"
        )
