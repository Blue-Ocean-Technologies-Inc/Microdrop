"""One block per action. Each block builds a QuickActionCtx with a
MagicMock pane and asserts:
  * on_execute_action(ctx) calls the right pane method (or constructs
    the dialog with the right args).
  * is_enabled(ctx) matrix is correct for the meaningful states.
The plugin's _contributed_quick_actions_default returns all 8 actions
in priority order.
"""

from unittest.mock import MagicMock

import pytest

from pluggable_protocol_tree.models.quick_action import QuickActionCtx
from pluggable_protocol_tree.models.row import GroupRow

from protocol_quick_action_tools.consts import (
    ACTION_ADD_GROUP, ACTION_ADD_STEP, ACTION_BROWSE_REPORTS,
    ACTION_DELETE_ROW, ACTION_IMPORT_PROTOCOL, ACTION_NEW_PROTOCOL,
    ACTION_OPEN_PROTOCOL, ACTION_SAVE_PROTOCOL,
)
from protocol_quick_action_tools.plugin import (
    ProtocolQuickActionToolsPlugin,
)
from protocol_quick_action_tools.quick_actions.add_group import (
    make_add_group_action,
)
from protocol_quick_action_tools.quick_actions.add_step import (
    make_add_step_action,
)
from protocol_quick_action_tools.quick_actions.browse_reports import (
    make_browse_reports_action,
)
from protocol_quick_action_tools.quick_actions.delete_row import (
    make_delete_row_action,
)
from protocol_quick_action_tools.quick_actions.import_protocol import (
    make_import_protocol_action,
)
from protocol_quick_action_tools.quick_actions.new_protocol import (
    make_new_protocol_action,
)
from protocol_quick_action_tools.quick_actions.open_protocol import (
    make_open_protocol_action,
)
from protocol_quick_action_tools.quick_actions.save_protocol import (
    make_save_protocol_action,
)


def _ctx(*, selected_paths=(), is_running=False, group=False,
         experiment_manager=True):
    pane = MagicMock()
    if group and selected_paths:
        pane.manager.get_row.return_value = GroupRow(name="G")
    else:
        pane.manager.get_row.return_value = MagicMock(spec=[])
    pane.experiment_manager = MagicMock() if experiment_manager else None
    return QuickActionCtx(pane=pane,
                          selected_paths=tuple(selected_paths),
                          is_running=is_running)


# --- add_step -----------------------------------------------------

def test_add_step_metadata():
    a = make_add_step_action()
    assert a.action_id == ACTION_ADD_STEP
    assert a.icon_text == "add"
    assert a.priority == 10
    assert a.shortcut == ""


def test_add_step_execute_calls_pane_helper():
    a = make_add_step_action()
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.add_step_after_selection.assert_called_once_with()


@pytest.mark.parametrize("running,expected",
                         [(False, True), (True, False)])
def test_add_step_is_enabled(running, expected):
    assert make_add_step_action().is_enabled(_ctx(is_running=running)) is expected


# --- delete_row ---------------------------------------------------

def test_delete_row_metadata():
    a = make_delete_row_action()
    assert a.action_id == ACTION_DELETE_ROW
    assert a.icon_text == "delete"
    assert a.priority == 20


def test_delete_row_execute_calls_pane_helper():
    a = make_delete_row_action()
    ctx = _ctx(selected_paths=[(0,)])
    a.on_execute_action(ctx)
    ctx.pane.delete_selected_rows.assert_called_once_with()


def test_delete_row_is_enabled_matrix():
    a = make_delete_row_action()
    assert a.is_enabled(_ctx()) is False                  # no selection
    assert a.is_enabled(_ctx(selected_paths=[(0,)])) is True
    assert a.is_enabled(_ctx(selected_paths=[(0,), (1,)])) is True
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              is_running=True)) is False


# --- add_group ----------------------------------------------------

def test_add_group_metadata():
    a = make_add_group_action()
    assert a.action_id == ACTION_ADD_GROUP
    assert a.icon_text == "playlist_add"
    assert a.priority == 30


def test_add_group_execute_calls_pane_helper():
    a = make_add_group_action()
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.add_group_after_selection.assert_called_once_with()


# --- import_protocol ----------------------------------------------

def test_import_protocol_metadata():
    a = make_import_protocol_action()
    assert a.action_id == ACTION_IMPORT_PROTOCOL
    assert a.icon_text == "unarchive"
    assert a.priority == 40


def test_import_protocol_execute_calls_pane_helper():
    a = make_import_protocol_action()
    ctx = _ctx(selected_paths=[(0,)], group=True)
    a.on_execute_action(ctx)
    ctx.pane.import_into_selected_group.assert_called_once_with()


def test_import_protocol_is_enabled_requires_single_group_selection():
    a = make_import_protocol_action()
    assert a.is_enabled(_ctx()) is False                       # no sel
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              group=False)) is False           # step, not group
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              group=True)) is True
    assert a.is_enabled(_ctx(selected_paths=[(0,), (1,)],
                              group=True)) is False            # multi-sel
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              group=True,
                              is_running=True)) is False


# --- open / save / new_protocol -----------------------------------

def test_open_protocol_calls_pane_helper():
    a = make_open_protocol_action()
    assert a.action_id == ACTION_OPEN_PROTOCOL
    assert a.icon_text == "file_open"
    assert a.priority == 50
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.load_protocol_dialog.assert_called_once_with()


def test_save_protocol_calls_pane_helper():
    a = make_save_protocol_action()
    assert a.action_id == ACTION_SAVE_PROTOCOL
    assert a.icon_text == "save"
    assert a.priority == 60
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.save_protocol_dialog.assert_called_once_with()


def test_new_protocol_calls_pane_helper():
    a = make_new_protocol_action()
    assert a.action_id == ACTION_NEW_PROTOCOL
    assert a.icon_text == "new_window"
    assert a.priority == 70
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.new_protocol.assert_called_once_with()


# --- browse_reports -----------------------------------------------

def test_browse_reports_metadata_and_shortcut():
    a = make_browse_reports_action()
    assert a.action_id == ACTION_BROWSE_REPORTS
    assert a.icon_text == "summarize"
    assert a.priority == 80
    assert a.shortcut == "R"


def test_browse_reports_execute_calls_pane_helper():
    a = make_browse_reports_action()
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.browse_reports_dialog.assert_called_once_with()


def test_browse_reports_disabled_without_experiment_manager():
    a = make_browse_reports_action()
    assert a.is_enabled(_ctx(experiment_manager=False)) is False
    assert a.is_enabled(_ctx(experiment_manager=True)) is True
    assert a.is_enabled(_ctx(experiment_manager=True,
                              is_running=True)) is False


# --- plugin default contributions list ----------------------------

def test_plugin_default_contributions_includes_all_eight_actions():
    plugin = ProtocolQuickActionToolsPlugin()
    contribs = plugin._contributed_quick_actions_default()
    ids = sorted(a.action_id for a in contribs)
    assert ids == sorted([
        ACTION_ADD_STEP, ACTION_DELETE_ROW, ACTION_ADD_GROUP,
        ACTION_IMPORT_PROTOCOL, ACTION_OPEN_PROTOCOL, ACTION_SAVE_PROTOCOL,
        ACTION_NEW_PROTOCOL, ACTION_BROWSE_REPORTS,
    ])
