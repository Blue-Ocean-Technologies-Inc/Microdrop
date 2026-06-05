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


def test_pane_returns_to_idle_after_protocol_finished(qapp, monkeypatch):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    # Monkeypatch publish_message to avoid Redis connection
    monkeypatch.setattr(ptp, "publish_message", lambda **kwargs: None)

    pane = ptp.ProtocolTreePane([make_type_column()])
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


def test_pane_phase_started_signal_sets_phase_timer(qapp):
    """Phase timing is driven by the executor's phase_started signal
    (independent of hardware ack), so the status bar tracks the executor
    regardless of whether an ack arrives."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._current_row = object()
    pane._step_timer.reset(running=False)
    pane.executor.qsignals.phase_started.emit(1, 3, 0.5)
    assert pane._phase_timer.running
    assert pane._step_timer.running          # phase_started starts the step timer too
    assert pane._phase_index == 1
    assert pane._phase_total == 3


def test_pane_phase_acked_is_noop_for_timer(qapp):
    """phase_acked no longer sets the phase timer — that moved to
    phase_started so external acks don't fight the executor-driven clock."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._current_row = object()
    pane._phase_timer.reset(running=False)
    pane.phase_acked.emit()
    assert not pane._phase_timer.running


def test_pane_protocol_error_resets_to_idle_and_calls_dialog(qapp, monkeypatch):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp

    calls = []

    def fake_error_dialog(parent=None, title="", message="", **kwargs):
        calls.append((title, message))

    monkeypatch.setattr(ptp, "error_dialog", fake_error_dialog)
    # _run_completion_flow("error") now runs after the dialog; patch confirm
    # and stop_logging so the test doesn't block on a modal or crash.
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.NO)

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
    # After the dedup fix, type/name are NOT in col_specs — they are encoded
    # in the fixed row-metadata fields (positions 2 and 3). The first ordinary
    # column is now "id" (the type/name builtins are filtered out).
    assert payload["columns"][0]["id"] == "id"


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


def test_pane_real_mode_new_experiment_updates_label_via_observer(qapp):
    """Clicking New Experiment with a real Traits-backed application
    triggers the experiment_changed observer, which updates the label
    — no explicit label update needed in the click handler."""
    from pathlib import Path
    from unittest.mock import MagicMock

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
    new_dir = Path("/tmp/2026-05-08T13-37-00Z")
    exp_mgr = MagicMock()
    exp_mgr.initialize_new_experiment.return_value = new_dir

    pane = ProtocolTreePane(
        [make_type_column()],
        application=app,
        experiment_manager=exp_mgr,
    )
    pane.btn_new_exp.click()
    assert app.current_experiment_directory == new_dir
    assert "2026-05-08T13-37-00Z" in pane.experiment_label.text()


def test_pane_closeEvent_detaches_experiment_changed_observer(qapp):
    """After closeEvent, the experiment_changed observer is unsubscribed
    so a subsequent fire doesn't dispatch to a deleted widget."""
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

    # Verify observer is wired pre-close.
    app.current_experiment_directory = "/tmp/before-close"
    assert "before-close" in pane.experiment_label.text()

    # Trigger close — observer must detach.
    from pyface.qt.QtGui import QCloseEvent
    pane.closeEvent(QCloseEvent())

    # Now firing should NOT update the label any more.
    pane.experiment_label.update_experiment_id("sentinel")
    app.current_experiment_directory = "/tmp/after-close"
    assert "after-close" not in pane.experiment_label.text()
    assert "sentinel" in pane.experiment_label.text()


def test_pane_accepts_device_viewer_sync_kwarg(qapp):
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    pane = ProtocolTreePane(
        [make_name_column()], device_viewer_sync=sync,
    )
    sync.attach.assert_called_once_with(pane.widget)


def test_pane_detaches_sync_on_close(qapp):
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    pane = ProtocolTreePane(
        [make_name_column()], device_viewer_sync=sync,
    )
    pane.close()
    sync.detach.assert_called_once()


def test_pane_without_sync_works(qapp):
    """Demo windows pass None - the pane stays usable."""
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    pane = ProtocolTreePane([make_name_column()])
    assert pane.device_viewer_sync is None


def test_pane_publishes_protocol_running_true_on_start(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    from device_viewer.consts import PROTOCOL_RUNNING
    pane = ProtocolTreePane([make_name_column()])
    pane._on_protocol_started()
    assert (PROTOCOL_RUNNING, "True") in publishes


def test_pane_publishes_protocol_running_false_on_finish(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    from device_viewer.consts import PROTOCOL_RUNNING
    pane = ProtocolTreePane([make_name_column()])
    pane._on_protocol_finished()
    assert (PROTOCOL_RUNNING, "False") in publishes


def test_pane_publishes_protocol_running_false_on_abort(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    from device_viewer.consts import PROTOCOL_RUNNING
    # _run_completion_flow("aborted") calls confirm(); patch it to avoid
    # a blocking modal dialog in headless tests.
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.NO)
    pane = ProtocolTreePane([make_name_column()])
    pane._on_protocol_aborted()
    assert (PROTOCOL_RUNNING, "False") in publishes


def test_select_step_does_not_suppress_sync_publish(qapp):
    """Nav buttons (next/prev/first/last) call _select_step. The user
    expects the DV to update on those clicks just as on a direct row
    click, so _select_step must NOT suppress the sync controller."""
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    sync._suppress_publish = False
    pane = ProtocolTreePane([make_name_column()], device_viewer_sync=sync)
    pane.manager.add_step(values={"name": "S1"})
    row = pane.manager.get_row((0,))

    seen_states = []
    original = pane.widget.tree.setCurrentIndex
    def capturing(idx):
        seen_states.append(sync._suppress_publish)
        return original(idx)
    pane.widget.tree.setCurrentIndex = capturing
    pane._select_step(row)

    assert seen_states == [False]
    assert sync._suppress_publish is False


def test_protocol_terminated_publishes_free_mode_to_dv(qapp):
    """When a protocol ends (finished or aborted), the pane should
    clear the selection AND push a free-mode payload to the DV so
    the user is back in free mode."""
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    sync._suppress_publish = False
    pane = ProtocolTreePane([make_name_column()], device_viewer_sync=sync)
    pane.manager.add_step(values={"name": "S1"})
    pane._on_protocol_terminated()
    sync._publish_for_row.assert_any_call(None)


def test_delete_selection_picks_alternative_step(qapp):
    """When the currently-selected step is deleted, an alternative step
    must be selected (whatever step is left). DV gets updated via the
    new selection's currentChanged."""
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    pane = ProtocolTreePane([make_name_column()])
    pane.manager.add_step(values={"name": "S1"})
    pane.manager.add_step(values={"name": "S2"})
    pane.manager.add_step(values={"name": "S3"})

    # Select S2, then delete it.
    pane._select_step(pane.manager.get_row((1,)))
    pane.manager.select([(1,)], mode="set")
    pane.widget._delete_selection()

    assert len(pane.manager.root.children) == 2
    cur_idx = pane.widget.tree.currentIndex()
    assert cur_idx.isValid()
    cur_path = pane.widget.index_to_path(cur_idx)
    assert cur_path == (0,) or cur_path == (1,)   # one of the surviving steps


def test_delete_all_steps_goes_to_free_mode(qapp):
    """Deleting the last step leaves no selection — free mode."""
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    pane = ProtocolTreePane([make_name_column()])
    pane.manager.add_step(values={"name": "S1"})
    pane._select_step(pane.manager.get_row((0,)))
    pane.manager.select([(0,)], mode="set")
    pane.widget._delete_selection()

    assert len(pane.manager.root.children) == 0
    assert not pane.widget.tree.currentIndex().isValid()


def test_on_step_started_does_not_publish_static_step_view(qapp):
    """Regression: step_started must NOT publish the static step view via
    _publish_for_row during a run.

    RoutesHandler publishes a per-phase display for every phase (carrying
    the full step context: step_id, label, routes, editable=False). The
    static _publish_for_row view (electrodes=[], editable=True) was
    published on step_started too, and — because the worker publishes
    phase 1 to the broker before the queued step_started slot runs — it
    consistently landed AFTER phase 1 and cleared it, so the animation
    appeared to begin at the second position. The per-phase displays are
    authoritative during execution; step_started must not clobber them."""
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    sync._suppress_publish = False
    pane = ProtocolTreePane([make_name_column()], device_viewer_sync=sync)
    pane.manager.add_step(values={"name": "S1"})
    row = pane.manager.get_row((0,))
    pane._on_step_started(row)
    sync._publish_for_row.assert_not_called()


def test_clear_highlights_suppresses_sync_publish(qapp):
    """clear_highlights also moves selection programmatically; same
    guard requirement."""
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    sync._suppress_publish = False
    pane = ProtocolTreePane([make_name_column()], device_viewer_sync=sync)

    seen_states = []
    original = pane.widget.tree.clearSelection
    def capturing():
        seen_states.append(sync._suppress_publish)
        return original()
    pane.widget.tree.clearSelection = capturing
    pane.clear_highlights()

    assert seen_states == [True]
    assert sync._suppress_publish is False    # restored


def test_format_error_html_from_step_execution_error():
    """The protocol-error dialog body is built as HTML from the structured
    StepExecutionError fields (step, column, hook, cause)."""
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    from pluggable_protocol_tree.execution.exceptions import StepExecutionError

    class _Model:
        col_name = "Magnet"
    class _Col:
        model = _Model()
    class _Row:
        path = (0, 1)          # -> "Step 1.2"
        name = "Engage magnet"

    exc = StepExecutionError(
        _Col(), "on_step", _Row(),
        TimeoutError("Timed out after 10.0s waiting for a reply on 'topic/x'."),
    )
    html = ProtocolTreePane._format_error_html(exc, "fallback")
    assert "Step 1.2" in html
    assert "Engage magnet" in html
    assert "Magnet" in html
    assert "on_step" in html
    assert "Timed out after 10.0s" in html
    assert "<p" in html and "</p>" in html       # it's HTML


def test_format_error_html_escapes_fallback():
    """Non-annotated errors fall back to the plain message, HTML-escaped."""
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    html = ProtocolTreePane._format_error_html(None, "<oops> & <crash>")
    assert "&lt;oops&gt;" in html
    assert "&amp;" in html
    assert "<oops>" not in html                  # raw angle brackets escaped


def test_pane_terminated_stops_logging(qapp):
    """The single terminal point drives logging stop (so one log spans all
    whole-protocol repetitions). With no experiment_manager, finished outcome
    skips the new-experiment prompt and calls stop_logging with generate_report=True."""
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    pane = ProtocolTreePane([make_type_column()])
    pane.logging_controller = MagicMock()
    pane._on_protocol_terminated()
    pane.logging_controller.stop_logging.assert_called_once_with(
        generate_report=True
    )


def test_flush_with_report_shows_progress_dialog_and_runs_in_worker(qapp, monkeypatch):
    """Legacy parity: when a report will be generated, the flush scheduler
    shows a 'Generating Run Report...' modal dialog and runs the flush
    in a QThread so the GUI stays responsive while plotly builds charts."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pyface.qt.QtCore import QThread

    shown = []
    class _FakeProgress:
        def __init__(self_, *a, **k): shown.append(("constructed",))
        def setWindowTitle(self_, t): shown.append(("title", t))
        def setWindowModality(self_, m): shown.append(("modality", m))
        def setCancelButton(self_, b): shown.append(("cancel", b))
        def show(self_): shown.append(("show",))
        def close(self_): shown.append(("close",))
    monkeypatch.setattr(ptp, "QProgressDialog", _FakeProgress)

    pane = ptp.ProtocolTreePane([make_name_column()])
    controller = pane.logging_controller
    # Force the fast (no-wait) path on the settling timer.
    controller._settling_provider = lambda: 0.0
    controller._generate_report = True
    flush_thread = {}

    def _fake_flush():
        # Capture the thread it ran on so we can assert it's NOT the GUI.
        flush_thread["t"] = QThread.currentThread()

    controller._flush = _fake_flush

    pane._schedule_flush_with_progress(controller)
    # The scheduler uses QTimer.singleShot(0, ...) + a nested QEventLoop;
    # processing events drains both.
    for _ in range(20):
        qapp.processEvents()

    assert ("show",) in shown
    assert ("title", "Please Wait") in shown
    assert ("close",) in shown
    assert flush_thread.get("t") is not None
    assert flush_thread["t"] is not QThread.currentThread()  # worker thread


def test_flush_progress_dialog_appears_before_settling_delay(qapp, monkeypatch):
    """No perceived pause between the new-experiment confirm and the
    "Generating Run Report..." dialog: the dialog must be shown
    synchronously inside `_schedule_flush_with_progress`, before any
    QTimer-scheduled callback fires (i.e. before any processEvents)."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    events = []
    class _FakeProgress:
        def __init__(self_, *a, **k): events.append("constructed")
        def setWindowTitle(self_, t): pass
        def setWindowModality(self_, m): pass
        def setCancelButton(self_, b): pass
        def show(self_): events.append("show")
        def close(self_): events.append("close")
    monkeypatch.setattr(ptp, "QProgressDialog", _FakeProgress)

    pane = ptp.ProtocolTreePane([make_name_column()])
    controller = pane.logging_controller
    # Pretend settling is non-trivial so the timer wouldn't have fired by
    # the time _schedule_flush_with_progress returns.
    controller._settling_provider = lambda: 5.0
    controller._generate_report = True
    controller._flush = lambda: None

    pane._schedule_flush_with_progress(controller)

    # Without ANY event processing yet, the dialog must already be shown.
    assert events[:2] == ["constructed", "show"]


def test_flush_without_report_skips_progress_dialog(qapp, monkeypatch):
    """Fast path: when no report is being generated (force-stop -> NO),
    skip the dialog and the worker thread entirely — flush just writes
    data files, so blocking on the GUI is fine and a dialog would be noise."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    shown = []
    class _FakeProgress:
        def __init__(self_, *a, **k): shown.append("constructed")
    monkeypatch.setattr(ptp, "QProgressDialog", _FakeProgress)

    pane = ptp.ProtocolTreePane([make_name_column()])
    controller = pane.logging_controller
    controller._settling_provider = lambda: 0.0
    controller._generate_report = False
    flushed = []
    controller._flush = lambda: flushed.append(True)

    pane._schedule_flush_with_progress(controller)
    for _ in range(5):
        qapp.processEvents()

    assert flushed == [True]
    assert shown == []                # dialog must NOT appear on fast path


def test_on_logging_complete_shows_success_with_link(qapp, monkeypatch, tmp_path):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    seen = {}
    monkeypatch.setattr(ptp, "success", lambda **k: seen.update(k))
    report = tmp_path / "exp dir" / "reports" / "report_x.html"   # space in path
    report.parent.mkdir(parents=True)
    report.write_text("<html></html>", encoding="utf-8")

    pane._on_logging_complete(report)
    assert "report_x.html" in seen.get("message", "")
    assert "file://" in seen.get("message", "")
    assert "%20" in seen.get("message", "")          # space percent-encoded, link not broken
    assert seen["title"] == "Run Summary Generated"


def test_on_logging_complete_none_shows_no_dialog(qapp, monkeypatch):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    calls = []
    monkeypatch.setattr(ptp, "success", lambda **k: calls.append(k))
    pane._on_logging_complete(None)
    assert calls == []


def _pane_for_flow(monkeypatch, *, with_exp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from unittest.mock import MagicMock

    kwargs = {}
    if with_exp:
        kwargs = {"application": MagicMock(), "experiment_manager": MagicMock()}
        kwargs["experiment_manager"].auto_save_protocol.return_value = None
    pane = ptp.ProtocolTreePane([make_name_column()], **kwargs)
    pane.logging_controller = MagicMock()
    pane._current_run_preview_mode = False
    pane._repeats_completed = 2
    return ptp, pane


def test_completion_flow_finished_prompts_new_experiment(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    from unittest.mock import MagicMock
    pane._on_new_experiment = MagicMock()
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.YES)

    pane._run_completion_flow("finished")

    pane._on_new_experiment.assert_called_once()
    pane.logging_controller.stop_logging.assert_called_once_with(generate_report=True)


def test_completion_flow_aborted_no_skips_report(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.NO)

    pane._run_completion_flow("aborted")

    pane.logging_controller.stop_logging.assert_called_once_with(generate_report=False)


def test_completion_flow_error_prompts_summary_like_abort(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.YES)

    pane._run_completion_flow("error")

    pane.logging_controller.stop_logging.assert_called_once_with(generate_report=True)


def test_completion_flow_preview_shows_info_no_confirm(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    pane._current_run_preview_mode = True
    counts = {"info": 0, "confirm": 0}
    monkeypatch.setattr(ptp, "information",
                        lambda **k: counts.__setitem__("info", counts["info"] + 1))
    monkeypatch.setattr(ptp, "confirm",
                        lambda **k: counts.__setitem__("confirm", counts["confirm"] + 1) or ptp.YES)

    pane._run_completion_flow("finished")

    assert counts == {"info": 1, "confirm": 0}
    pane.logging_controller.stop_logging.assert_called_once_with()


def test_completion_flow_no_experiment_manager_skips_autosave_and_prompt(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=False)
    confirms = []
    monkeypatch.setattr(ptp, "confirm", lambda **k: confirms.append(k) or ptp.YES)

    pane._run_completion_flow("finished")

    assert confirms == []          # no "Create New Experiment?" without a manager
    pane.logging_controller.stop_logging.assert_called_once_with(generate_report=True)


def test_completion_flow_finished_autosave_logs_protocol_path(qapp, monkeypatch, tmp_path):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    saved = tmp_path / "protocols" / "protocol_x.json"
    saved.parent.mkdir(parents=True)
    saved.write_text("{}", encoding="utf-8")
    pane.experiment_manager.auto_save_protocol.return_value = saved
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.NO)   # don't start a new experiment

    pane._run_completion_flow("finished")

    pane.logging_controller.log_metadata.assert_called_once()
    (arg,), _ = pane.logging_controller.log_metadata.call_args
    assert "Protocol Path" in arg
    assert "protocol_x.json" in arg["Protocol Path"]


def test_completion_flow_aborted_no_experiment_manager_skips_summary_prompt(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=False)
    confirms = []
    monkeypatch.setattr(ptp, "confirm", lambda **k: confirms.append(k) or ptp.NO)

    pane._run_completion_flow("aborted")

    assert confirms == []          # no summary prompt without an experiment manager
    pane.logging_controller.stop_logging.assert_called_once_with(generate_report=True)


def test_terminated_error_outcome_defers_completion_flow(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    ran = []
    pane._run_completion_flow = lambda outcome: ran.append(outcome)
    pane._on_protocol_terminated("error")
    assert ran == []                      # error: flow deferred to _on_error


def test_terminated_finished_outcome_runs_completion_flow(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    ran = []
    pane._run_completion_flow = lambda outcome: ran.append(outcome)
    pane._on_protocol_terminated("finished")
    assert ran == ["finished"]


def test_on_error_shows_dialog_before_completion_flow(qapp, monkeypatch):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    order = []
    pane._publish_protocol_running = lambda *a, **k: None
    pane._on_protocol_terminated = lambda outcome="finished": order.append(("term", outcome))
    pane._run_completion_flow = lambda outcome: order.append(("flow", outcome))
    monkeypatch.setattr(ptp, "error_dialog", lambda **k: order.append("error_dialog"))

    pane._on_error("boom")

    assert order == [("term", "error"), "error_dialog", ("flow", "error")]


def test_pane_emits_protocol_running_changed_true_on_start(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    seen = []
    pane.protocol_running_changed.connect(lambda v: seen.append(v))
    pane._on_protocol_started()
    assert seen == [True]


def test_pane_emits_protocol_running_changed_false_on_terminated(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    seen = []
    pane.protocol_running_changed.connect(lambda v: seen.append(v))
    pane._on_protocol_terminated()
    assert seen == [False]


def test_pane_emits_selection_changed_on_tree_selection(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pyface.qt.QtCore import QItemSelection
    pane = ptp.ProtocolTreePane([make_name_column()])
    fired = []
    pane.selection_changed.connect(lambda: fired.append(True))
    # Drive the tree's selectionModel directly — pane subscribes to
    # selectionChanged and re-emits the parameterless selection_changed.
    sm = pane.widget.tree.selectionModel()
    sm.selectionChanged.emit(QItemSelection(), QItemSelection())
    assert fired == [True]


def test_pane_mounts_quick_action_bar_when_actions_passed(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.quick_action import BaseQuickAction

    a = BaseQuickAction(action_id="add_step", icon_text="add",
                        tooltip="Add step", priority=10)
    b = BaseQuickAction(action_id="save_protocol", icon_text="save",
                        tooltip="Save", priority=60)
    pane = ptp.ProtocolTreePane([make_name_column()], quick_actions=[a, b])
    assert pane.quick_action_bar is not None
    assert set(pane.quick_action_bar.buttons.keys()) == {"add_step", "save_protocol"}
    assert pane.quick_actions_controller is not None


def test_pane_skips_quick_action_bar_when_no_actions(qapp):
    """No actions contributed (e.g. demo, headless test) -> no bar
    widget mounted; controller is None. This is the architectural
    commitment: the tree plugin ships zero builtins."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    assert pane.quick_action_bar is None
    assert pane.quick_actions_controller is None


def _pane_with_two_steps(qapp):
    """Pane with a tree containing exactly two top-level step rows."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    # seed_default_step_if_empty already gave us 1 step; add one more.
    pane.manager.add_step()
    return pane


def test_add_step_after_selection_with_no_selection_appends_root(qapp):
    pane = _pane_with_two_steps(qapp)
    before = len(pane.manager.root.children)
    pane.manager.selection = []
    pane.add_step_after_selection()
    assert len(pane.manager.root.children) == before + 1


def test_add_step_after_selection_with_one_selected_inserts_below(qapp):
    pane = _pane_with_two_steps(qapp)
    pane.manager.selection = [(0,)]
    before = len(pane.manager.root.children)
    pane.add_step_after_selection()
    assert len(pane.manager.root.children) == before + 1


def test_add_group_after_selection_appends_a_group(qapp):
    pane = _pane_with_two_steps(qapp)
    pane.manager.selection = []
    before = len(pane.manager.root.children)
    pane.add_group_after_selection()
    assert len(pane.manager.root.children) == before + 1
    from pluggable_protocol_tree.models.row import GroupRow
    assert isinstance(pane.manager.root.children[-1], GroupRow)


def test_delete_selected_rows_removes_at_those_paths(qapp):
    pane = _pane_with_two_steps(qapp)
    before = len(pane.manager.root.children)
    pane.manager.selection = [(0,)]
    pane.delete_selected_rows()
    assert len(pane.manager.root.children) == before - 1


def test_delete_selected_rows_no_selection_is_noop(qapp):
    pane = _pane_with_two_steps(qapp)
    before = len(pane.manager.root.children)
    pane.manager.selection = []
    pane.delete_selected_rows()
    assert len(pane.manager.root.children) == before


def test_import_into_selected_group_noop_when_no_group_selected(qapp,
                                                                 monkeypatch):
    """Selection points to a step (not a group) -> import is a no-op."""
    pane = _pane_with_two_steps(qapp)
    pane.manager.selection = [(0,)]            # a step row
    called = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog."
        "getOpenFileName",
        lambda *a, **k: called.append(True) or ("", ""))
    pane.import_into_selected_group()
    assert called == []                        # never even opened the dialog


def test_import_into_selected_group_adds_top_level_rows(qapp, tmp_path,
                                                         monkeypatch):
    """Selecting a group + importing -> the imported protocol's
    top-level rows are merged under the selected group. Nested rows
    are NOT recursively imported."""
    import json as _json
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.models.row_manager import RowManager

    # Build a target pane with one group selected.
    cols = [make_type_column(), make_name_column()]
    pane = ptp.ProtocolTreePane(cols)
    target_path = pane.manager.add_group(name="Dest")
    pane.manager.selection = [tuple(target_path)]

    # Build an "imported" protocol via the actual serializer: one
    # top-level step and one top-level group (the group's nested
    # contents must be ignored per the deep-import-out-of-scope rule).
    src = RowManager(columns=cols)
    src.add_step(values={"name": "imported_step"})
    inner_group = src.add_group(name="ImportedGroup")
    src.add_step(parent_path=inner_group, values={"name": "should_be_skipped"})
    file_data = src.to_json()
    f = tmp_path / "p.json"
    f.write_text(_json.dumps(file_data), encoding="utf-8")

    # Stub the file-dialog to return our file.
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog."
        "getOpenFileName",
        lambda *a, **k: (str(f), ""))

    pane.import_into_selected_group()

    # The target group now has exactly two new direct children:
    # the imported step and the imported (empty) group.
    dest = pane.manager.get_row(target_path)
    assert len(dest.children) == 2
    # First merged child: the step.
    assert dest.children[0].row_type == "step"
    assert dest.children[0].name == "imported_step"
    # Second merged child: the group, but with NO children.
    assert dest.children[1].row_type == "group"
    assert dest.children[1].name == "ImportedGroup"
    assert len(dest.children[1].children) == 0


def test_import_into_selected_group_noop_on_unreadable_file(qapp,
                                                              monkeypatch):
    """A broken file selection -> the method returns without raising
    and without mutating the tree."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    target_path = pane.manager.add_group(name="Dest")
    pane.manager.selection = [tuple(target_path)]

    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog."
        "getOpenFileName",
        lambda *a, **k: ("/non/existent.json", ""))

    before = len(pane.manager.get_row(target_path).children)
    pane.import_into_selected_group()                # must not raise
    after = len(pane.manager.get_row(target_path).children)
    assert before == after


def test_delete_last_step_removes_last_top_level_step(qapp):
    """Two top-level steps -> delete_last_step removes the second one."""
    pane = _pane_with_two_steps(qapp)        # helper from Task 8 already exists
    before = len(pane.manager.root.children)
    # No selection — the action's new behaviour is independent of selection.
    pane.manager.selection = []
    pane.delete_last_step()
    assert len(pane.manager.root.children) == before - 1


def test_delete_last_step_descends_into_groups(qapp):
    """Last child is a group containing a step -> delete the step
    inside the group, leaving the (now-empty) group in place."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    # The pane starts with an empty tree. Add a top-level step, then a
    # group containing one step so the last execution step is nested.
    pane.manager.add_step()                            # step at (0,)
    group_path = pane.manager.add_group(name="G")      # group at (1,)
    pane.manager.add_step(parent_path=group_path)      # step at (1, 0)
    # Tree now: step(0,) / Group(step(1,0))
    group = pane.manager.get_row(group_path)
    assert len(group.children) == 1            # sanity

    pane.delete_last_step()

    # The nested step inside G must be gone; G itself must remain.
    group = pane.manager.get_row(group_path)
    assert len(group.children) == 0
    # And the top-level step is untouched.
    assert len(pane.manager.root.children) == 2  # original step + empty group


def test_delete_last_step_empty_tree_is_noop(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    # The pane starts with an empty tree (no auto-seeding in __init__).
    assert len(pane.manager.root.children) == 0
    pane.delete_last_step()                    # must not raise


def test_delete_last_step_empty_trailing_group_deletes_the_group(qapp):
    """`S1, EmptyGroup` -> delete removes the empty group, leaves S1."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    pane.manager.add_step()                       # S1
    group_path = pane.manager.add_group(name="G")
    assert len(pane.manager.root.children) == 2

    pane.delete_last_step()

    assert len(pane.manager.root.children) == 1
    from pluggable_protocol_tree.models.row import GroupRow
    # The remaining row is the step (S1), NOT the group.
    assert not isinstance(pane.manager.root.children[0], GroupRow)


def test_delete_last_step_non_empty_group_descends_to_step(qapp):
    """`S1, Group[S2, S3]` -> delete removes S3, leaving Group[S2]."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    pane.manager.add_step()                       # S1 at (0,)
    group_path = pane.manager.add_group(name="G")
    pane.manager.add_step(parent_path=group_path) # S2
    pane.manager.add_step(parent_path=group_path) # S3
    group = pane.manager.get_row(group_path)
    assert len(group.children) == 2

    pane.delete_last_step()

    group = pane.manager.get_row(group_path)
    assert len(group.children) == 1               # S3 gone, S2 remains
    assert len(pane.manager.root.children) == 2   # S1 + G(S2)


def test_delete_last_step_nested_empty_group_deletes_inner_empty_group(qapp):
    """`S1, Group[S2, EmptyInnerGroup]` -> delete removes the inner
    empty group, leaving Group[S2]."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.row import GroupRow
    pane = ptp.ProtocolTreePane([make_name_column()])
    pane.manager.add_step()
    group_path = pane.manager.add_group(name="G")
    pane.manager.add_step(parent_path=group_path)
    pane.manager.add_group(parent_path=group_path, name="Inner")
    group = pane.manager.get_row(group_path)
    assert len(group.children) == 2
    assert isinstance(group.children[-1], GroupRow)
    assert len(group.children[-1].children) == 0

    pane.delete_last_step()

    group = pane.manager.get_row(group_path)
    assert len(group.children) == 1
    # Remaining is the step inside G — the inner empty group is gone.
    assert not isinstance(group.children[0], GroupRow)


def test_add_step_after_selection_with_group_selected_appends_inside_group(qapp):
    """Single-group selection -> new step lands inside the group, not
    at the root level after it."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    pane.manager.add_step()                       # step at (0,)
    group_path = pane.manager.add_group(name="G") # group at (1,)
    pane.manager.selection = [tuple(group_path)]

    pane.add_step_after_selection()

    group = pane.manager.get_row(group_path)
    assert len(group.children) == 1               # new step is inside G
    # Top-level layout unchanged: still just step + group.
    assert len(pane.manager.root.children) == 2


def test_add_group_after_selection_with_group_selected_appends_inside_group(qapp):
    """Same rule applies to add_group: single-group selection -> the
    new group nests inside as a sub-group."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.row import GroupRow
    pane = ptp.ProtocolTreePane([make_name_column()])
    pane.manager.add_step()
    group_path = pane.manager.add_group(name="G")
    pane.manager.selection = [tuple(group_path)]

    pane.add_group_after_selection()

    group = pane.manager.get_row(group_path)
    assert len(group.children) == 1
    assert isinstance(group.children[0], GroupRow)
    assert len(pane.manager.root.children) == 2


def test_add_step_after_selection_with_multi_selection_uses_last(qapp):
    """Multi-selection with the last being a group does NOT trigger
    the "append inside" rule — only single-group selection does."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    pane.manager.add_step()                       # step at (0,)
    group_path = pane.manager.add_group(name="G") # group at (1,)
    # Select both — multi-selection.
    pane.manager.selection = [(0,), tuple(group_path)]

    pane.add_step_after_selection()

    # New step is at root level (after the group), NOT inside G.
    group = pane.manager.get_row(group_path)
    assert len(group.children) == 0
    assert len(pane.manager.root.children) == 3


def test_add_step_after_selection_with_nested_group_selected_appends_inside(qapp):
    """A nested group is still a group — selecting it appends inside,
    same as a top-level group."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    outer = pane.manager.add_group(name="Outer")
    inner = pane.manager.add_group(parent_path=outer, name="Inner")
    pane.manager.selection = [tuple(inner)]

    pane.add_step_after_selection()

    inner_row = pane.manager.get_row(inner)
    outer_row = pane.manager.get_row(outer)
    assert len(inner_row.children) == 1            # step inside Inner
    assert len(outer_row.children) == 1            # Outer still has only Inner


def test_import_into_selected_group_robust_to_schema_field_order(qapp,
                                                                  tmp_path,
                                                                  monkeypatch):
    """If a saved file ever reorders the leading-metadata fields,
    the importer must still merge correctly because positions are
    looked up by name, not hardcoded."""
    import json as _json
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    pane = ptp.ProtocolTreePane(
        [make_type_column(), make_name_column()])
    target_path = pane.manager.add_group(name="Dest")
    pane.manager.selection = [tuple(target_path)]

    # Synthetic file: shuffle the fixed metadata around so
    # `depth` is at position 1 and `type` is at position 0,
    # plus one ordinary column at position 3.
    file_data = {
        "schema_version": 1,
        "protocol_metadata": {},
        "row_flags": {},
        "columns": [],
        "fields": ["type", "depth", "name", "uuid"],
        "rows": [
            ["step", 0, "imported_step", "u-1"],
            ["group", 0, "imported_group", "u-2"],
            ["step", 1, "nested_skip", "u-3"],   # nested -> skipped
        ],
    }
    f = tmp_path / "p.json"
    f.write_text(_json.dumps(file_data), encoding="utf-8")
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog."
        "getOpenFileName",
        lambda *a, **k: (str(f), ""))

    pane.import_into_selected_group()

    dest = pane.manager.get_row(target_path)
    assert len(dest.children) == 2
    assert dest.children[0].row_type == "step"
    assert dest.children[0].name == "imported_step"
    assert dest.children[1].row_type == "group"
    assert dest.children[1].name == "imported_group"
    assert len(dest.children[1].children) == 0


def test_attempt_func_execution_returns_wrapped_value_on_success(qapp):
    """Successful call passes through the wrapped function's return value
    with no dialog."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp

    calls = []
    ptp_error = ptp.error

    class _Fake:
        @ptp.attempt_func_execution_with_error_dialog
        def do(self, x, y):
            return x + y

    f = _Fake()
    # Sanity: the dialog is NOT invoked on success. Replace it with a
    # tripwire that fails the test if called.
    try:
        ptp.error = lambda *a, **k: calls.append("BUG: dialog called on success")
        assert f.do(2, 3) == 5
    finally:
        ptp.error = ptp_error
    assert calls == []


def test_attempt_func_execution_shows_html_dialog_and_logs_on_exception(
    qapp, monkeypatch, caplog):
    """Exception path: dialog gets HTML informative + traceback detail,
    logger captures the stack, and the wrapper returns None instead of
    propagating."""
    import logging
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp

    captured = {}

    def _fake_error(parent, *, message, title, informative=None, detail=None,
                    **kw):
        captured["parent"] = parent
        captured["message"] = message
        captured["title"] = title
        captured["informative"] = informative
        captured["detail"] = detail

    monkeypatch.setattr(ptp, "error", _fake_error)
    caplog.set_level(logging.ERROR, logger="pluggable_protocol_tree.views.protocol_tree_pane")

    class _Fake:
        @ptp.attempt_func_execution_with_error_dialog
        def save_protocol_dialog(self):
            raise ValueError("disk full")

    result = _Fake().save_protocol_dialog()
    assert result is None
    # Message + title use the humanised operation name and the exception
    # type — both readable to a user.
    assert captured["title"] == "Save Protocol Dialog Error"
    assert "Save Protocol Dialog" in captured["message"]
    assert "ValueError" in captured["message"]
    # Informative is HTML, bold name, red exception type, escaped cause.
    assert "<b>Save Protocol Dialog</b>" in captured["informative"]
    assert "ValueError" in captured["informative"]
    assert "disk full" in captured["informative"]
    # Detail contains the full traceback (multi-line, includes "Traceback").
    assert "Traceback" in captured["detail"]
    assert "ValueError: disk full" in captured["detail"]
    # Logger captured it too, with exc_info.
    assert any(
        "Save Protocol Dialog failed" in r.message and r.exc_info
        for r in caplog.records)


def test_attempt_func_execution_handles_dialog_failure_gracefully(
    qapp, monkeypatch, caplog):
    """If the dialog itself raises (e.g. no Qt event loop), we log it
    but the wrapper does NOT propagate — original exception was already
    logged so the caller can carry on."""
    import logging
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp

    def _broken_error(*a, **k):
        raise RuntimeError("no event loop")

    monkeypatch.setattr(ptp, "error", _broken_error)
    caplog.set_level(logging.ERROR, logger="pluggable_protocol_tree.views.protocol_tree_pane")

    class _Fake:
        @ptp.attempt_func_execution_with_error_dialog
        def do(self):
            raise IOError("boom")

    # No exception propagates.
    assert _Fake().do() is None
    # Both the original error AND the dialog failure were logged.
    messages = " | ".join(r.message for r in caplog.records)
    assert "Do failed: boom" in messages
    assert "failed to show error dialog" in messages


def test_attempt_func_execution_html_escapes_exception_message(qapp,
                                                                monkeypatch):
    """Exception message containing HTML special chars must be escaped
    so the dialog renders it as text, not markup."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp

    captured = {}
    monkeypatch.setattr(ptp, "error",
                        lambda parent, **k: captured.update(k))

    class _Fake:
        @ptp.attempt_func_execution_with_error_dialog
        def do(self):
            raise RuntimeError("<script>alert('x')</script>")

    _Fake().do()
    # The raw script tag must NOT appear; escaped form must.
    assert "<script>" not in captured["informative"]
    assert "&lt;script&gt;" in captured["informative"]


def test_import_into_selected_group_skips_none_values(qapp, tmp_path,
                                                       monkeypatch):
    """A saved row with None for a strict-typed column (e.g. Float)
    must NOT raise TraitError on import — the None is skipped so the
    trait keeps its default. Regression for the bug reported on
    feat/433."""
    import json as _json
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )

    cols = [make_name_column(), make_duration_column()]
    pane = ptp.ProtocolTreePane(cols)
    target_path = pane.manager.add_group(name="Dest")
    pane.manager.selection = [tuple(target_path)]

    # Synthetic file: duration is None — strict Float trait rejects it
    # with a naive setattr. Importer must skip and let the default apply.
    file_data = {
        "schema_version": 1,
        "protocol_metadata": {}, "row_flags": {},
        "columns": [
            {"id": "name", "cls": "x.NameColumnModel"},
            {"id": "duration_s", "cls": "x.DurationColumnModel"},
        ],
        "fields": ["depth", "uuid", "type", "name", "duration_s"],
        "rows": [
            [0, "u-1", "step", "imported_step", None],
        ],
    }
    f = tmp_path / "p.json"
    f.write_text(_json.dumps(file_data), encoding="utf-8")
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog."
        "getOpenFileName",
        lambda *a, **k: (str(f), ""))

    pane.import_into_selected_group()                # must not raise

    dest = pane.manager.get_row(target_path)
    assert len(dest.children) == 1
    new_step = dest.children[0]
    assert new_step.name == "imported_step"
    # duration kept its default (not None — the row class has a defined
    # Float default, typically 1.0). Just assert it's a float (not None).
    assert isinstance(new_step.duration_s, float)


def test_import_into_selected_group_skips_columns_not_in_live_set(qapp,
                                                                    tmp_path,
                                                                    monkeypatch):
    """A saved column id absent from the LIVE column set must be
    skipped rather than becoming an orphan attribute on the row."""
    import json as _json
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    # Live tree has only the name column.
    pane = ptp.ProtocolTreePane([make_name_column()])
    target_path = pane.manager.add_group(name="Dest")
    pane.manager.selection = [tuple(target_path)]

    file_data = {
        "schema_version": 1,
        "protocol_metadata": {}, "row_flags": {},
        "columns": [
            {"id": "name", "cls": "x.NameColumnModel"},
            {"id": "unknown_plugin_col", "cls": "x.WhateverModel"},
        ],
        "fields": ["depth", "uuid", "type", "name", "unknown_plugin_col"],
        "rows": [
            [0, "u-1", "step", "ok_step", "junk-value"],
        ],
    }
    f = tmp_path / "p.json"
    f.write_text(_json.dumps(file_data), encoding="utf-8")
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog."
        "getOpenFileName",
        lambda *a, **k: (str(f), ""))

    pane.import_into_selected_group()

    dest = pane.manager.get_row(target_path)
    assert len(dest.children) == 1
    new_step = dest.children[0]
    assert new_step.name == "ok_step"
    # The unknown column id must NOT have leaked onto the row as an
    # orphan attribute.
    assert not hasattr(new_step, "unknown_plugin_col")


def test_refresh_status_running_index_without_total(qapp):
    """Dynamic VT loop: phase_total == 0 but phase_index > 0 -> show the
    running phase number with NO denominator."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._current_row = object()
    pane._step_timer.reset(running=True)
    pane._phase_timer.reset(running=True)
    pane._phase_index = 7
    pane._phase_total = 0
    pane._phase_target = 1.0
    pane._refresh_status()
    text = pane._status_phase_time_label.text()
    assert "Phase 7" in text
    assert "Phase 7/" not in text          # no denominator


def test_refresh_status_index_over_total_when_known(qapp):
    """Static/count path: phase_total > 0 -> unchanged 'i/N' rendering."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._current_row = object()
    pane._step_timer.reset(running=True)
    pane._phase_timer.reset(running=True)
    pane._phase_index = 2
    pane._phase_total = 5
    pane._phase_target = 0.5
    pane._refresh_status()
    assert "Phase 2/5" in pane._status_phase_time_label.text()


