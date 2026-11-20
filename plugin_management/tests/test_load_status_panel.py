# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The load-status panel model, and the indicator and panel built
standalone against fake records."""

# Third-party imports.
import pytest

# Microdrop package imports.
from plugin_management.consts import PLUGIN_LOAD_STATE_GLYPHS
from plugin_management.load_status_model import PluginLoadStatusPanelModel

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import (
    LOAD_FAILED,
    LOAD_LOADED,
    LOAD_LOADING,
    PluginLoadStatus,
)


def _fake_status():
    status = PluginLoadStatus()
    status.mark_pending("good.plugin", "Good Plugin")
    status.mark_pending("broken.plugin", "Broken Plugin")
    status.get_record("good.plugin").trait_set(state=LOAD_LOADED, duration=0.25)
    status.mark_failed(
        "broken.plugin",
        "RuntimeError: no device",
        "Traceback (most recent call last):\nRuntimeError: no device",
    )

    return status


@pytest.fixture
def qapp():
    from pyface.qt.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_opening_selects_the_first_failure_and_details_show_its_traceback():
    model = PluginLoadStatusPanelModel(status=_fake_status())

    assert model.details_text == "Select a plugin to see its details."

    model.select_first_failure()

    assert model.selected.plugin_id == "broken.plugin"
    assert "failed to start" in model.details_text
    assert "Traceback (most recent call last)" in model.details_text


def test_details_of_a_loaded_plugin_give_its_start_time():
    status = _fake_status()
    model = PluginLoadStatusPanelModel(status=status, selected=status.records[0])

    assert model.details_text == "Good Plugin (good.plugin) started in 0.250 s."


def test_a_dropped_record_is_deselected():
    status = _fake_status()
    model = PluginLoadStatusPanelModel(status=status)
    model.select_first_failure()

    status.discard("broken.plugin")

    assert model.selected is None


def test_indicator_follows_the_aggregate_state(qapp):
    from plugin_management.load_status_view import PluginLoadStatusIndicator

    status = _fake_status()
    indicator = PluginLoadStatusIndicator(status=status)

    assert indicator.widget.text() == PLUGIN_LOAD_STATE_GLYPHS[LOAD_FAILED]
    assert "1 failed" in indicator.widget.toolTip()

    status.mark_pending("later.plugin")

    assert indicator.widget.text() == PLUGIN_LOAD_STATE_GLYPHS[LOAD_LOADING]
    assert indicator._pulsing

    status.discard("later.plugin")
    status.discard("broken.plugin")

    assert indicator.widget.text() == PLUGIN_LOAD_STATE_GLYPHS[LOAD_LOADED]
    assert not indicator._pulsing


def test_panel_builds_standalone_against_its_model(qapp):
    from plugin_management.load_status_view import PluginLoadStatusView

    model = PluginLoadStatusPanelModel(status=_fake_status())
    model.select_first_failure()

    ui = model.edit_traits(view=PluginLoadStatusView)

    try:
        assert ui.control is not None
    finally:
        ui.dispose()
