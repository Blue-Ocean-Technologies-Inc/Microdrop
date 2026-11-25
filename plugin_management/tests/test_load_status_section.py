# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The plugin load list as a notifications pane section, and the loading
indicator opening that section when the notifications plugin runs, its own
panel otherwise. Nothing is published: the publisher is replaced."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Microdrop package imports.
from notifications.consts import NOTIFICATIONS_PLUGIN_ID
from plugin_management import plugin as plugin_module
from plugin_management.consts import LOAD_STATUS_SECTION_ID
from plugin_management.load_status_section import PluginLoadStatusSection
from plugin_management.plugin import PluginManagementPlugin

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import LOAD_LOADED, PluginLoadStatus


@pytest.fixture
def qapp():
    from pyface.qt.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_section_summary_follows_the_load_records():
    status = PluginLoadStatus()
    section = PluginLoadStatusSection(status=status)
    status.mark_pending("a.plugin", "A")

    assert section.id == LOAD_STATUS_SECTION_ID
    assert section.summary == "0 plugins loaded, 1 loading"

    status.get_record("a.plugin").state = LOAD_LOADED

    assert section.summary == "1 plugins loaded"


def test_the_section_contents_list_the_records_and_follow_additions(qapp):
    status = PluginLoadStatus()
    status.mark_failed("b.plugin", "RuntimeError: no", "Traceback ...", name="B")
    section = PluginLoadStatusSection(status=status)

    contents = section.factory(None)

    try:
        assert contents.table.rowCount() == 1
        assert contents.table.item(0, 1).text() == "B"
        assert contents.model.selected.plugin_id == "b.plugin"

        status.mark_pending("a.plugin", "A")

        # The rows are rebuilt once per burst of changes, on the event loop.
        qapp.processEvents()

        assert contents.table.rowCount() == 2
        assert contents.table.item(1, 1).text() == "A"

    finally:
        contents.dispose()
        contents.deleteLater()


class _Recorder:
    def __init__(self):
        self.calls = []

    def publish(self, payload):
        self.calls.append(payload)

    def show_panel(self, parent):
        self.calls.append(("panel", parent))


def _plugin_stand_in(loaded_plugin_ids, recorder):
    """What ``_show_load_status`` reads from its plugin."""
    window = object()
    application = SimpleNamespace(
        get_plugin=lambda plugin_id: (
            object() if plugin_id in loaded_plugin_ids else None
        )
    )
    indicator = SimpleNamespace(widget=SimpleNamespace(window=lambda: window))

    return SimpleNamespace(
        application=application,
        _load_status_indicator=indicator,
        _load_status_controller=recorder,
    ), window


def test_the_indicator_opens_the_notifications_section_when_it_runs(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(plugin_module, "show_notifications_panel_publisher", recorder)
    stand_in, _window = _plugin_stand_in({NOTIFICATIONS_PLUGIN_ID}, recorder)

    PluginManagementPlugin._show_load_status(stand_in)

    assert recorder.calls == [{"section_id": LOAD_STATUS_SECTION_ID}]


def test_the_indicator_opens_its_own_panel_without_notifications(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(plugin_module, "show_notifications_panel_publisher", recorder)
    stand_in, window = _plugin_stand_in(set(), recorder)

    PluginManagementPlugin._show_load_status(stand_in)

    assert recorder.calls == [("panel", window)]
