# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for PluggableProtocolDockPane — the composition root that owns
the executor, the status controller, the logging controller, and all
run control (issue #471 moved this off ProtocolTreePane, the pure view
it drives).

Retargeted from test_protocol_tree_pane.py (issue #663): those 33 tests
described behaviour that still exists, just moved. Most changes here are
"construct a dock pane instead of a bare pane, read the attribute off the
dock pane instead of the pane" — not rewrites.
"""

# Standard library imports.
from types import SimpleNamespace
from unittest.mock import MagicMock

# Third-party imports.
import pytest

# Enthought library imports.
from envisage.ui.tasks.api import TasksApplication, TaskWindow
from pyface.tasks.api import Task
from traits.api import Any, Event

# Microdrop package imports.
from pluggable_protocol_tree.services.logging.controller import (
    ProtocolLoggingController,
)


def _mock_of(cls):
    """A MagicMock that satisfies isinstance(mock, cls) — needed for a
    strictly-typed Instance(cls) trait — without MagicMock(spec=cls)'s
    dir(cls)-based attribute restriction, which only sees a Traits class's
    *class*-level attributes, not the instance traits added by the
    HasTraits metaclass (e.g. DeviceViewerSyncController.phase_nav_mode is
    invisible to dir(DeviceViewerSyncController) but very much a real
    trait)."""
    mock = MagicMock()
    mock.__class__ = cls
    return mock


class _StubApplication(TasksApplication):
    """Just enough of the real MicrodropApplication for the dock pane's
    class-level ``@observe("task.window.application...")`` decorators to
    resolve at construction time. The real application declares the same
    two traits as filesystem/Redis-backed Properties (see
    microdrop_application/application.py) — overkill, and side-effecting,
    for a pure unit test."""

    experiment_changed = Event()
    current_experiment_directory = Any(None)


@pytest.fixture
def build_dock_pane():
    """Factory fixture: build a headless PluggableProtocolDockPane per
    call (real Task/TaskWindow/TasksApplication chain, no plugins, no
    Redis), tearing every one down at test end so its background poll
    scheduler thread doesn't outlive the test.

    ``sync`` defaults to a MagicMock: DeviceViewerSyncController.__init__
    registers a dramatiq actor, which only tolerates being constructed
    once per process — real syncing is DeviceViewerSyncController's own
    concern, not the dock pane's, and no test here needs it.
    """
    from pluggable_protocol_tree.services.device_viewer_sync import (
        DeviceViewerSyncController,
    )
    from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane

    panes = []

    def _build(columns=None, **kwargs):
        if columns is None:
            from pluggable_protocol_tree.builtins.name_column import (
                make_name_column,
            )

            columns = [make_name_column()]

        # sync is strictly Instance(DeviceViewerSyncController); _mock_of
        # makes it pass Traits' isinstance validation. phase_nav_mode is
        # pinned False so a bare MagicMock's (truthy) auto-attribute
        # doesn't silently route idle-phase-nav-only code paths
        # (_idle_nav_active) differently from a real, freshly-built sync.
        if "sync" not in kwargs:
            sync = _mock_of(DeviceViewerSyncController)
            sync.phase_nav_mode = False
            kwargs["sync"] = sync

        task = Task()
        task.window = TaskWindow(application=_StubApplication())

        dock_pane = PluggableProtocolDockPane(columns=columns, task=task, **kwargs)
        dock_pane.create_contents(parent=None)
        panes.append(dock_pane)

        return dock_pane

    yield _build

    for pane in panes:
        pane.destroy()


class FakePausableRow:
    """Row stub rich enough for the pause-time phase computation."""

    path = [0]
    name = "S"
    duration_s = 1.0
    electrodes = []
    routes = []
    trail_length = 1
    trail_overlay = 0
    soft_start = False
    soft_end = False
    repeat_duration = 0.0
    linear_repeats = False
    repetitions = 1


# --- executor ownership -------------------------------------------------


def test_dock_pane_has_executor_and_pause_event(build_dock_pane):
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor

    dock_pane = build_dock_pane()
    assert isinstance(dock_pane.executor, ProtocolExecutor)
    assert dock_pane.executor.pause_event is not None
    assert dock_pane.executor.stop_event is not None


def test_dock_pane_executor_can_be_overridden(build_dock_pane):
    """The pane's old executor_factory kwarg is gone with the executor
    itself (issue #471) — the equivalent substitution point is now the
    dock pane's own `executor` trait, settable like any other. `executor`
    is strictly Instance(ProtocolExecutor); spec= makes a MagicMock pass
    that validation while still satisfying the wiring contract
    (create_contents observes a handful of `executor.signals.*` events)."""
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor

    fake_executor = _mock_of(ProtocolExecutor)
    dock_pane = build_dock_pane(executor=fake_executor)
    assert dock_pane.executor is fake_executor


# --- button state machine -----------------------------------------------


def test_dock_pane_running_button_state_after_protocol_started(build_dock_pane):
    dock_pane = build_dock_pane()
    dock_pane.executor.signals.protocol_started = True
    nb = dock_pane._pane.navigation_bar
    assert nb.btn_stop.isEnabled()
    for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
        assert not btn.isEnabled()


def test_dock_pane_returns_to_idle_after_protocol_finished(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)

    # protocol_finished runs the completion flow, which — with an experiment
    # manager — would prompt "Start a new experiment?" via a real (blocking)
    # confirm() dialog; experiment_manager=None skips that branch entirely
    # (have_exp is False), which is all this test cares about anyway.
    dock_pane = build_dock_pane(experiment_manager=None)
    dock_pane.executor.signals.protocol_started = True
    dock_pane.executor.signals.protocol_finished = True
    nb = dock_pane._pane.navigation_bar
    assert not nb.btn_stop.isEnabled()


def test_dock_pane_protocol_error_resets_to_idle_and_calls_dialog(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    calls = []

    def fake_error_dialog(parent=None, title="", message="", **kwargs):
        calls.append((title, message))

    monkeypatch.setattr(dp, "error_dialog", fake_error_dialog)
    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)
    # _run_completion_flow("error") runs after the dialog; patch confirm so
    # the test doesn't block on a modal.
    monkeypatch.setattr(dp, "confirm", lambda **k: dp.NO)

    dock_pane = build_dock_pane()
    dock_pane.executor.signals.protocol_started = True
    assert dock_pane._pane.navigation_bar.btn_stop.isEnabled()
    dock_pane.executor.signals.protocol_error = "kaboom"
    assert not dock_pane._pane.navigation_bar.btn_stop.isEnabled()
    assert calls == [("Protocol error", "kaboom")]


def test_dock_pane_pause_splits_play_button_into_phase_nav(build_dock_pane):
    dock_pane = build_dock_pane()
    dock_pane._current_row = FakePausableRow()
    dock_pane.executor.signals.protocol_started = True
    dock_pane.executor.signals.protocol_paused = True
    assert dock_pane._pane.navigation_bar.is_phase_navigation_active()


def test_dock_pane_resume_merges_phase_nav_back_to_play_button(build_dock_pane):
    dock_pane = build_dock_pane()
    dock_pane._current_row = FakePausableRow()
    dock_pane.executor.signals.protocol_started = True
    dock_pane.executor.signals.protocol_paused = True
    assert dock_pane._pane.navigation_bar.is_phase_navigation_active()
    dock_pane.executor.signals.protocol_resumed = True
    assert not dock_pane._pane.navigation_bar.is_phase_navigation_active()


# --- phase navigation -----------------------------------------------------


def test_dock_pane_phase_nav_publishes_electrodes_state_change(
    build_dock_pane, monkeypatch
):
    """next_phase click delegates to the status controller, which publishes
    ELECTRODES_STATE_CHANGE for the targeted phase (#471)."""
    import pluggable_protocol_tree.services.protocol_status_controller as psc
    import pluggable_protocol_tree.views.dock_pane as dp
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column
    from pluggable_protocol_tree.services.protocol_status_controller import (
        ProtocolStatusController,
    )

    captured = []

    def fake_publish(topic, message, **kwargs):
        captured.append((topic, message))

    # Phase nav publishes from the controller module, not the dock pane.
    monkeypatch.setattr(psc, "publish_message", fake_publish)

    from pluggable_protocol_tree.builtins.name_column import make_name_column

    dock_pane = build_dock_pane(columns=[make_name_column(), make_routes_column()])
    manager = dock_pane.manager
    # A step whose route expands to >1 phase so Next has somewhere to go.
    path = manager.add_step(values={"routes": [["e1", "e2"]]})
    row = manager.get_row(path)
    manager.protocol_metadata["electrode_to_channel"] = {"e1": 1, "e2": 2}

    sc = ProtocolStatusController(
        signals=None, manager=manager, executor=dock_pane.executor
    )
    dock_pane.status_controller = sc
    sc.model.on_protocol_start(0.0, 1)
    sc.model.on_step_start(0.0, 1, 1, tuple(row.path), row.name, "-")
    sc.model.on_phase_start(0.0, 1, sc._phase_total_for(row), 1.0)
    sc.model.pause(0.0)
    dock_pane._current_row = row

    dock_pane._on_next_phase()
    assert captured  # something was published
    assert any(topic == dp.ELECTRODES_STATE_CHANGE for topic, _ in captured)


# --- step-cursor navigation ------------------------------------------------


def test_dock_pane_navigate_to_first_step_selects_first_row(build_dock_pane):
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dock_pane = build_dock_pane(
        columns=[
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
    )
    dock_pane.manager.add_step(values={"name": "A", "duration_s": 0.1})
    dock_pane.manager.add_step(values={"name": "B", "duration_s": 0.1})
    dock_pane.navigate_to_first_step()
    idx = dock_pane._pane.widget.tree.currentIndex()
    assert idx.isValid()


def test_dock_pane_navigate_to_next_at_end_duplicates_step(build_dock_pane):
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dock_pane = build_dock_pane(
        columns=[
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
    )
    # create_contents already seeded one default step (legacy protocol_grid
    # parity — full-app-only behaviour a bare pane never had); "A" is added
    # after it, so the tree starts with 2 steps, not 1.
    dock_pane.manager.add_step(values={"name": "A", "duration_s": 0.1})
    dock_pane.navigate_to_last_step()
    dock_pane.navigate_to_next_step()
    assert len(dock_pane.manager.root.children) == 3


# --- protocol_running publishing + protocol_running_changed signal -------


def test_dock_pane_publishes_protocol_running_true_on_start(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    publishes = []
    monkeypatch.setattr(
        dp,
        "publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from device_viewer.consts import PROTOCOL_RUNNING

    dock_pane = build_dock_pane()
    dock_pane._on_protocol_started()
    assert (PROTOCOL_RUNNING, "True") in publishes


def test_dock_pane_publishes_protocol_running_false_on_finish(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    publishes = []
    monkeypatch.setattr(
        dp,
        "publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from device_viewer.consts import PROTOCOL_RUNNING

    # experiment_manager=None: see test_dock_pane_returns_to_idle_after_
    # protocol_finished — avoids the completion flow's real (blocking)
    # confirm() dialog for a test that only cares about the publish.
    dock_pane = build_dock_pane(experiment_manager=None)
    dock_pane._on_protocol_finished()
    assert (PROTOCOL_RUNNING, "False") in publishes


def test_dock_pane_publishes_protocol_running_false_on_abort(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    publishes = []
    monkeypatch.setattr(
        dp,
        "publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from device_viewer.consts import PROTOCOL_RUNNING

    # _run_completion_flow("aborted") may prompt via confirm(); patch it to
    # avoid a blocking modal dialog in headless tests.
    monkeypatch.setattr(dp, "confirm", lambda **k: dp.NO)
    dock_pane = build_dock_pane()
    dock_pane._on_protocol_aborted()
    assert (PROTOCOL_RUNNING, "False") in publishes


def test_dock_pane_protocol_terminated_publishes_free_mode_to_dv(
    build_dock_pane, monkeypatch
):
    """When a protocol ends, the dock pane pushes a free-mode payload to
    the DV so the user is back in free mode."""
    import pluggable_protocol_tree.views.dock_pane as dp

    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)
    monkeypatch.setattr(dp, "confirm", lambda **k: dp.NO)

    dock_pane = build_dock_pane()  # sync is a MagicMock by default
    dock_pane.manager.add_step(values={"name": "S1"})
    dock_pane._on_protocol_terminated()
    dock_pane.sync._publish_for_row.assert_any_call(None)


def test_dock_pane_emits_protocol_running_changed_true_on_start(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)
    dock_pane = build_dock_pane()
    seen = []
    dock_pane._pane.protocol_running_changed.connect(lambda v: seen.append(v))
    dock_pane._on_protocol_started()
    assert seen == [True]


def test_dock_pane_emits_protocol_running_changed_false_on_terminated(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)
    monkeypatch.setattr(dp, "confirm", lambda **k: dp.NO)
    dock_pane = build_dock_pane()
    seen = []
    dock_pane._pane.protocol_running_changed.connect(lambda v: seen.append(v))
    dock_pane._on_protocol_terminated()
    assert seen == [False]


# --- error-dialog HTML formatting ------------------------------------------


def test_format_error_html_from_step_execution_error():
    """The protocol-error dialog body is built as HTML from the structured
    StepExecutionError fields (step, column, hook, cause)."""
    from pluggable_protocol_tree.execution.exceptions import StepExecutionError
    from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane

    class _Model:
        col_name = "Magnet"

    class _Col:
        model = _Model()

    class _Row:
        path = (0, 1)  # -> "Step 1.2"
        name = "Engage magnet"

        def dotted_path(self):
            # mirrors BaseRow.dotted_path
            return ".".join(str(i + 1) for i in self.path)

    exc = StepExecutionError(
        _Col(),
        "on_step",
        _Row(),
        TimeoutError("Timed out after 10.0s waiting for a reply on 'topic/x'."),
    )
    html = PluggableProtocolDockPane._format_error_html(exc, "fallback")
    assert "Step 1.2" in html
    assert "Engage magnet" in html
    assert "Magnet" in html
    assert "on_step" in html
    assert "Timed out after 10.0s" in html
    assert "<p" in html and "</p>" in html  # it's HTML


def test_format_error_html_escapes_fallback():
    """Non-annotated errors fall back to the plain message, HTML-escaped."""
    from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane

    html = PluggableProtocolDockPane._format_error_html(None, "<oops> & <crash>")
    assert "&lt;oops&gt;" in html
    assert "&amp;" in html
    assert "<oops>" not in html  # raw angle brackets escaped


# --- logging + completion flow ---------------------------------------------


def test_dock_pane_terminated_stops_logging(build_dock_pane, monkeypatch):
    """The single terminal point drives logging stop (so one log spans all
    whole-protocol repetitions). With no experiment_manager, finished
    outcome skips the new-experiment prompt and calls stop_logging with
    generate_report=True."""
    import pluggable_protocol_tree.views.dock_pane as dp

    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)
    dock_pane = build_dock_pane(experiment_manager=None)
    dock_pane.logging_controller = _mock_of(ProtocolLoggingController)
    dock_pane.logging_controller.has_data.return_value = True  # a step ran
    dock_pane._on_protocol_terminated()
    dock_pane.logging_controller.stop_logging.assert_called_once_with(
        generate_report=True
    )


def _dock_pane_for_flow(build_dock_pane, *, with_exp):
    from pluggable_protocol_tree.services.experiment_manager import ExperimentManager

    kwargs = {}
    if with_exp:
        exp_mgr = _mock_of(ExperimentManager)
        exp_mgr.auto_save_protocol.return_value = None
        kwargs["experiment_manager"] = exp_mgr
    else:
        kwargs["experiment_manager"] = None

    dock_pane = build_dock_pane(**kwargs)
    dock_pane.logging_controller = _mock_of(ProtocolLoggingController)
    # The run executed steps, so the report is offered/generated; has_data()
    # gates that (a run stopped before any step logs nothing -> no report).
    dock_pane.logging_controller.has_data.return_value = True
    dock_pane._current_run_preview_mode = False

    return dock_pane


def test_completion_flow_finished_prompts_new_experiment(build_dock_pane, monkeypatch):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = _dock_pane_for_flow(build_dock_pane, with_exp=True)
    dock_pane._pane._on_new_experiment = MagicMock()
    monkeypatch.setattr(dp, "confirm", lambda **k: dp.YES)

    dock_pane._run_completion_flow("finished")

    dock_pane._pane._on_new_experiment.assert_called_once()
    dock_pane.logging_controller.stop_logging.assert_called_once_with(
        generate_report=True
    )


def test_completion_flow_aborted_no_skips_report(build_dock_pane, monkeypatch):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = _dock_pane_for_flow(build_dock_pane, with_exp=True)
    monkeypatch.setattr(dp, "confirm", lambda **k: dp.NO)

    dock_pane._run_completion_flow("aborted")

    dock_pane.logging_controller.stop_logging.assert_called_once_with(
        generate_report=False
    )


def test_completion_flow_error_prompts_summary_like_abort(build_dock_pane, monkeypatch):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = _dock_pane_for_flow(build_dock_pane, with_exp=True)
    monkeypatch.setattr(dp, "confirm", lambda **k: dp.YES)

    dock_pane._run_completion_flow("error")

    dock_pane.logging_controller.stop_logging.assert_called_once_with(
        generate_report=True
    )


def test_completion_flow_preview_shows_info_no_confirm(build_dock_pane, monkeypatch):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = _dock_pane_for_flow(build_dock_pane, with_exp=True)
    dock_pane._current_run_preview_mode = True
    counts = {"info": 0, "confirm": 0}
    monkeypatch.setattr(
        dp,
        "information",
        lambda **k: counts.__setitem__("info", counts["info"] + 1),
    )
    monkeypatch.setattr(
        dp,
        "confirm",
        lambda **k: counts.__setitem__("confirm", counts["confirm"] + 1) or dp.YES,
    )

    dock_pane._run_completion_flow("finished")

    assert counts == {"info": 1, "confirm": 0}
    dock_pane.logging_controller.stop_logging.assert_called_once_with()


def test_completion_flow_no_experiment_manager_skips_autosave_and_prompt(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = _dock_pane_for_flow(build_dock_pane, with_exp=False)
    confirms = []
    monkeypatch.setattr(dp, "confirm", lambda **k: confirms.append(k) or dp.YES)

    dock_pane._run_completion_flow("finished")

    assert confirms == []  # no "Create New Experiment?" without a manager
    dock_pane.logging_controller.stop_logging.assert_called_once_with(
        generate_report=True
    )


def test_completion_flow_finished_autosave_logs_protocol_path(
    build_dock_pane, monkeypatch, tmp_path
):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = _dock_pane_for_flow(build_dock_pane, with_exp=True)
    saved = tmp_path / "protocols" / "protocol_x.json"
    saved.parent.mkdir(parents=True)
    saved.write_text("{}", encoding="utf-8")
    dock_pane.experiment_manager.auto_save_protocol.return_value = saved
    monkeypatch.setattr(
        dp, "confirm", lambda **k: dp.NO
    )  # don't start a new experiment

    dock_pane._run_completion_flow("finished")

    dock_pane.logging_controller.log_metadata.assert_called_once()
    (arg,), _ = dock_pane.logging_controller.log_metadata.call_args
    assert "Protocol Path" in arg
    assert "protocol_x.json" in arg["Protocol Path"]


def test_completion_flow_aborted_no_experiment_manager_skips_summary_prompt(
    build_dock_pane, monkeypatch
):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = _dock_pane_for_flow(build_dock_pane, with_exp=False)
    confirms = []
    monkeypatch.setattr(dp, "confirm", lambda **k: confirms.append(k) or dp.NO)

    dock_pane._run_completion_flow("aborted")

    assert confirms == []  # no summary prompt without an experiment manager
    dock_pane.logging_controller.stop_logging.assert_called_once_with(
        generate_report=True
    )


def test_terminated_error_outcome_defers_completion_flow(build_dock_pane, monkeypatch):
    import pluggable_protocol_tree.views.dock_pane as dp

    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)
    dock_pane = build_dock_pane()
    ran = []
    dock_pane._run_completion_flow = lambda outcome: ran.append(outcome)
    dock_pane._on_protocol_terminated("error")
    assert ran == []  # error: flow deferred to _on_error


def test_terminated_finished_outcome_runs_completion_flow(build_dock_pane, monkeypatch):
    import pluggable_protocol_tree.views.dock_pane as dp

    monkeypatch.setattr(dp, "publish_message", lambda **kwargs: None)
    dock_pane = build_dock_pane()
    ran = []
    dock_pane._run_completion_flow = lambda outcome: ran.append(outcome)
    dock_pane._on_protocol_terminated("finished")
    assert ran == ["finished"]


def test_on_error_shows_dialog_before_completion_flow(build_dock_pane, monkeypatch):
    import pluggable_protocol_tree.views.dock_pane as dp

    dock_pane = build_dock_pane()
    order = []
    dock_pane._publish_protocol_running = lambda *a, **k: None
    dock_pane._on_protocol_terminated = lambda outcome="finished": order.append(
        ("term", outcome)
    )
    dock_pane._run_completion_flow = lambda outcome: order.append(("flow", outcome))
    monkeypatch.setattr(dp, "error_dialog", lambda **k: order.append("error_dialog"))

    dock_pane._on_error(SimpleNamespace(new="boom"))

    assert order == [("term", "error"), "error_dialog", ("flow", "error")]


# --- quick-actions controller ownership -------------------------------------


def test_dock_pane_mounts_quick_action_bar_when_actions_passed(build_dock_pane):
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.quick_action import BaseQuickAction

    a = BaseQuickAction(
        action_id="add_step", icon_text="add", tooltip="Add step", priority=10
    )
    b = BaseQuickAction(
        action_id="save_protocol", icon_text="save", tooltip="Save", priority=60
    )
    dock_pane = build_dock_pane(columns=[make_name_column()], quick_actions=[a, b])
    pane = dock_pane._pane
    assert pane.quick_action_bar is not None
    assert set(pane.quick_action_bar.buttons.keys()) == {"add_step", "save_protocol"}
    assert pane.quick_actions_controller is not None
