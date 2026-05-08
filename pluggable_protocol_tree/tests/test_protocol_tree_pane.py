"""Tests for ProtocolTreePane — the reusable host widget for the
pluggable protocol tree's full UX (navigation, status, experiment
bar, executor, button state machine)."""


def test_pane_constructs_with_columns_list(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
    ])
    assert pane.manager is not None
    ids = [c.model.col_id for c in pane.manager.columns]
    assert ids == ["type", "id", "name"]


def test_pane_constructs_with_existing_manager(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    rm = RowManager(columns=[make_type_column()])
    pane = ProtocolTreePane(rm)
    assert pane.manager is rm


def test_pane_has_tree_widget(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

    pane = ProtocolTreePane([make_type_column()])
    assert isinstance(pane.widget, ProtocolTreeWidget)


def test_pane_has_navigation_bar_with_play_button(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.navigation_bar is not None
    assert pane.navigation_bar.btn_play is not None


def test_pane_has_status_bar(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.status_bar is not None
    assert pane.status_bar.lbl_step_progress.text() == "Step 0/0"


def test_pane_has_experiment_bar_widgets(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.btn_new_exp is not None
    assert pane.btn_new_note is not None
    assert isinstance(pane.experiment_label, ExperimentLabel)


def test_pane_phase_ack_topic_default_is_electrodes_state_applied(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.phase_ack_topic == ELECTRODES_STATE_APPLIED


def test_pane_phase_ack_topic_can_be_none(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic=None)
    assert pane.phase_ack_topic is None
    assert pane.status_bar.lbl_phase_time.isVisible() is False


def test_pane_has_executor_and_pause_event(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert isinstance(pane.executor, ProtocolExecutor)
    assert pane.executor.pause_event is not None
    assert pane.executor.stop_event is not None


def test_pane_executor_factory_can_be_overridden(qapp):
    """The executor_factory kwarg lets tests substitute the executor.
    The factory's return value must satisfy the wiring contract — a
    bare object() would break _wire_executor_signals — so use a
    MagicMock that exposes the attributes the wiring touches."""
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    fake_executor = MagicMock()
    captured = {}

    def fake_factory(row_manager, qsignals, pause_event, stop_event):
        captured["called"] = True
        return fake_executor

    pane = ProtocolTreePane([make_type_column()], executor_factory=fake_factory)
    assert captured["called"] is True
    assert pane.executor is fake_executor


def test_pane_idle_button_state(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    nb = pane.navigation_bar
    assert nb.btn_play.isEnabled()
    assert not nb.btn_stop.isEnabled()
    for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
        assert btn.isEnabled()


def test_pane_running_button_state_after_protocol_started(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    pane.executor.qsignals.protocol_started.emit()
    nb = pane.navigation_bar
    assert nb.btn_stop.isEnabled()
    for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
        assert not btn.isEnabled()


def test_pane_returns_to_idle_after_protocol_finished(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    pane.executor.qsignals.protocol_started.emit()
    pane.executor.qsignals.protocol_finished.emit()
    nb = pane.navigation_bar
    assert not nb.btn_stop.isEnabled()


def test_pane_step_started_updates_status_label(qapp):
    """Emitting step_started increments the step counter label."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeRow:
        path = []
        name = "Step A"
        duration_s = 0.0

    pane = ProtocolTreePane([make_type_column()])
    pane._step_total = 3
    pane.executor.qsignals.step_started.emit(FakeRow())
    assert pane._status_step_label.text() == "Step 1 / 3"


def test_pane_tick_timer_runs_at_10_hz(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane._tick_timer.interval() == 100


def test_pane_phase_acked_signal_resets_phase_timer(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._current_row = object()
    pane._step_started_at = None
    pane.phase_acked.emit()
    assert pane._phase_started_at is not None
    assert pane._step_started_at is not None


def test_pane_protocol_error_resets_to_idle_and_calls_dialog(qapp, monkeypatch):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp

    calls = []

    def fake_error_dialog(parent=None, title="", message="", **kwargs):
        calls.append((title, message))

    monkeypatch.setattr(ptp, "error_dialog", fake_error_dialog)

    pane = ptp.ProtocolTreePane([make_type_column()])
    pane.executor.qsignals.protocol_started.emit()
    assert pane.navigation_bar.btn_stop.isEnabled()
    pane.executor.qsignals.protocol_error.emit("kaboom")
    assert not pane.navigation_bar.btn_stop.isEnabled()
    assert not pane._tick_timer.isActive()
    assert calls == [("Protocol error", "kaboom")]


def test_pane_pause_splits_play_button_into_phase_nav(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeRow:
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

    pane = ProtocolTreePane([make_type_column()])
    pane._current_row = FakeRow()
    pane.executor.qsignals.protocol_started.emit()
    pane.executor.qsignals.protocol_paused.emit()
    assert pane.navigation_bar.is_phase_navigation_active()


def test_pane_resume_merges_phase_nav_back_to_play_button(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeRow:
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

    pane = ProtocolTreePane([make_type_column()])
    pane._current_row = FakeRow()
    pane.executor.qsignals.protocol_started.emit()
    pane.executor.qsignals.protocol_paused.emit()
    assert pane.navigation_bar.is_phase_navigation_active()
    pane.executor.qsignals.protocol_resumed.emit()
    assert not pane.navigation_bar.is_phase_navigation_active()


def test_pane_phase_nav_publishes_electrodes_state_change(qapp, monkeypatch):
    """next_phase click publishes ELECTRODES_STATE_CHANGE for the targeted phase."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    captured = []

    def fake_publish(topic, message, **kwargs):
        captured.append((topic, message))

    monkeypatch.setattr(ptp, "publish_message", fake_publish)

    pane = ptp.ProtocolTreePane([make_type_column()])
    pane._pause_phases = [{"e1"}, {"e1", "e2"}]
    pane._pause_phase_idx = 0
    pane.manager.protocol_metadata["electrode_to_channel"] = {"e1": 1, "e2": 2}
    pane._on_next_phase()
    assert captured  # something was published
    topic, _ = captured[0]
    assert topic == ptp.ELECTRODES_STATE_CHANGE


def test_pane_navigate_to_first_step_selects_first_row(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
    ])
    pane.manager.add_step(values={"name": "A", "duration_s": 0.1})
    pane.manager.add_step(values={"name": "B", "duration_s": 0.1})
    pane.navigate_to_first_step()
    idx = pane.widget.tree.currentIndex()
    assert idx.isValid()


def test_pane_navigate_to_next_at_end_duplicates_step(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
    ])
    pane.manager.add_step(values={"name": "A", "duration_s": 0.1})
    pane.navigate_to_last_step()
    pane.navigate_to_next_step()
    assert len(pane.manager.root.children) == 2


def test_pane_save_writes_manager_to_json(qapp, tmp_path, monkeypatch):
    from pyface.qt.QtWidgets import QFileDialog

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    import json

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
    ])
    pane.manager.add_step(values={"name": "S1", "duration_s": 0.1})

    save_path = tmp_path / "out.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **kw: (str(save_path), ""))
    pane.save_to_dialog()
    payload = json.loads(save_path.read_text())
    assert payload["columns"][0]["id"] == "type"


def test_pane_stub_mode_buttons_log_only(qapp):
    """Without injected services, button clicks log and never raise."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    pane.btn_new_exp.click()
    pane.btn_new_note.click()
    pane.experiment_label.clicked.emit()


def test_pane_real_mode_new_experiment_calls_service(qapp):
    """With an experiment_manager + application, New Experiment dispatches."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    new_dir = Path("/tmp/new-exp-id")
    exp_mgr = MagicMock()
    exp_mgr.initialize_new_experiment.return_value = new_dir
    exp_mgr.get_experiment_directory.return_value = new_dir

    app = MagicMock()
    app.current_experiment_directory = Path("/tmp/old-exp-id")

    pane = ProtocolTreePane(
        [make_type_column()],
        application=app,
        experiment_manager=exp_mgr,
    )
    pane.btn_new_exp.click()
    exp_mgr.initialize_new_experiment.assert_called_once()
    assert app.current_experiment_directory == new_dir


def test_pane_real_mode_new_experiment_returning_none_does_not_overwrite(qapp):
    from pathlib import Path
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    exp_mgr = MagicMock()
    exp_mgr.initialize_new_experiment.return_value = None
    app = MagicMock()
    app.current_experiment_directory = Path("/tmp/old-exp-id")

    pane = ProtocolTreePane(
        [make_type_column()],
        application=app,
        experiment_manager=exp_mgr,
    )
    pane.btn_new_exp.click()
    assert app.current_experiment_directory == Path("/tmp/old-exp-id")


def test_pane_real_mode_new_note_calls_sticky_manager(qapp):
    from pathlib import Path
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    base_dir = Path("/tmp/exp-1")
    exp_mgr = MagicMock()
    exp_mgr.get_experiment_directory.return_value = base_dir
    sticky_mgr = MagicMock()

    pane = ProtocolTreePane(
        [make_type_column()],
        experiment_manager=exp_mgr,
        sticky_manager=sticky_mgr,
    )
    pane.btn_new_note.click()
    sticky_mgr.request_new_note.assert_called_once_with(base_dir, "exp-1")


def test_pane_real_mode_label_click_opens_experiment_directory(qapp):
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    exp_mgr = MagicMock()
    pane = ProtocolTreePane(
        [make_type_column()],
        experiment_manager=exp_mgr,
    )
    pane.experiment_label.clicked.emit()
    exp_mgr.open_experiment_directory.assert_called_once()


def test_pane_observes_experiment_changed_event_to_update_label(qapp):
    """When application.experiment_changed fires, the label re-reads
    application.current_experiment_directory and updates."""
    from pathlib import Path

    from traits.api import Directory, Event, HasTraits, Property

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeApp(HasTraits):
        current_experiment_directory = Property(Directory)
        experiment_changed = Event()
        _value = Path("/tmp/initial")

        def _get_current_experiment_directory(self):
            return self._value

        def _set_current_experiment_directory(self, value):
            self._value = Path(value)
            self.experiment_changed = True

    app = FakeApp()
    pane = ProtocolTreePane([make_type_column()], application=app)
    app.current_experiment_directory = "/tmp/2026-05-08T12-00-00Z"
    assert "2026-05-08T12-00-00Z" in pane.experiment_label.text()
