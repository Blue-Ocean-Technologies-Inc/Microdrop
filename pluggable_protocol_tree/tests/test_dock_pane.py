"""Tests for PluggableProtocolDockPane wiring."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_dock_pane_with_mocked_app(qapp, columns):
    """Returns (dock_pane, app_stub, mock_task) with the task->window->
    application chain attached at construction — traits_init seeds the
    ack-wait preferences and needs the chain immediately (matching
    production, where the dock-pane factory is called with task=task).

    window/application are HasTraits stubs, not MagicMocks: the dock
    pane's @observe("task.window.application...") chains traverse them
    at task-assignment time, and traits observation can't walk a mock.
    """
    from apptools.preferences.api import Preferences
    from pyface.tasks.api import Task
    from traits.api import Any, Event, HasTraits
    from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane

    class _AppStub(HasTraits):
        preferences = Any()
        current_experiment_directory = Any()
        experiment_changed = Event()

    class _WindowStub(HasTraits):
        application = Any()
        closing = Event()

    app_stub = _AppStub(
        # Real (in-memory) preferences node: the dock pane binds
        # ProtocolPreferences against it, whose trait validates
        # IPreferences.
        preferences=Preferences(),
        current_experiment_directory=Path("/tmp/exp-1"),
    )
    # spec=Task so the strict Instance(Task) trait validator accepts it.
    mock_task = MagicMock(spec=Task)
    mock_task.window = _WindowStub(application=app_stub)

    dp = PluggableProtocolDockPane(columns=columns, task=mock_task)
    return dp, app_stub, mock_task


def test_dock_pane_id_and_name(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    dp, _, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    assert dp.id == "pluggable_protocol_tree.dock_pane"
    assert dp.name == "Protocol (pluggable)"


def test_dock_pane_create_contents_returns_protocol_tree_pane(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    dp, _, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    contents = dp.create_contents(parent=None)
    assert isinstance(contents, ProtocolTreePane)


def test_dock_pane_constructs_experiment_manager_with_app_dir(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dp, app, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    with patch(
        "pluggable_protocol_tree.views.dock_pane.ExperimentManager"
    ) as ExpMgrClass:
        dp.create_contents(parent=None)
    ExpMgrClass.assert_called_once_with(app.current_experiment_directory)


def test_dock_pane_constructs_sticky_manager(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dp, _, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    with patch(
        "pluggable_protocol_tree.views.dock_pane.StickyWindowManager"
    ) as StickyClass:
        dp.create_contents(parent=None)
    StickyClass.assert_called_once_with()


def test_dock_pane_passes_application_into_pane(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dp, app, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    contents = dp.create_contents(parent=None)
    assert contents.application is app


def test_dock_pane_passes_device_viewer_sync_to_pane(qapp):
    """The dock pane in the full app constructs a DeviceViewerSyncController
    and passes it to the ProtocolTreePane."""
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.services.device_viewer_sync import (
        DeviceViewerSyncController,
    )

    dp, _, _ = _make_dock_pane_with_mocked_app(qapp, [make_name_column()])
    contents = dp.create_contents(parent=None)

    assert isinstance(contents.device_viewer_sync, DeviceViewerSyncController)


def test_dock_pane_seeds_default_step_on_startup(qapp):
    """Legacy protocol_grid parity (issue #424): opening the dock pane with
    no protocol loaded starts with one default step, treated as a clean
    baseline (not flagged as unsaved)."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    dp, _, _ = _make_dock_pane_with_mocked_app(
        qapp, [make_type_column(), make_name_column()])
    contents = dp.create_contents(parent=None)
    assert len(contents.manager.root.children) == 1
    assert contents.manager.root.children[0].row_type == "step"
    assert contents.protocol_state_tracker.is_modified is False
