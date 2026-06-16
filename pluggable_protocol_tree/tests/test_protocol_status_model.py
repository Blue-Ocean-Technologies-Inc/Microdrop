"""Unit tests for ProtocolStatusModel (pure, fake-clock, no Qt)."""
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel


def test_protocol_start_sets_total_and_runs():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=3)
    assert m.step_total == 3
    assert m.step_index == 0
    assert m.running is True
    assert m.protocol_clock.elapsed(2.0) == 2.0


def test_step_start_increments_and_resets_phase():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=3)
    m.on_step_start(0.0, "Step A", "Step B")
    assert m.step_index == 1
    assert m.recent_step_name == "Step A"
    assert m.next_step_name == "Step B"
    assert m.phase_index == 0
    assert m.phase_total == 0
    assert m.step_clock.elapsed(1.0) == 1.0
    m.on_step_start(1.0, "Step B", "-")
    assert m.step_index == 2
    # step clock restarted at t=1.0
    assert m.step_clock.elapsed(3.0) == 2.0


def test_phase_start_sets_counts_and_target():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, "A", "-")
    m.on_phase_start(0.0, phase_index=2, phase_total=4, phase_target_s=1.5)
    assert m.phase_index == 2
    assert m.phase_total == 4
    assert m.phase_target_s == 1.5
    assert m.phase_clock.elapsed(0.5) == 0.5
    m.on_phase_extended(0.5)
    assert m.phase_target_s == 2.0


def test_pause_freezes_active_not_elapsed_all_scopes():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, "A", "-")
    m.on_phase_start(0.0, 1, 1, 1.0)
    m.pause(1.0)
    assert m.paused is True
    # elapsed keeps going, active frozen at 1.0
    assert m.protocol_clock.elapsed(5.0) == 5.0
    assert m.protocol_clock.active(5.0) == 1.0
    assert m.step_clock.active(5.0) == 1.0
    assert m.phase_clock.active(5.0) == 1.0
    m.resume(5.0)
    assert m.paused is False
    assert m.protocol_clock.active(6.0) == 2.0


def test_step_start_while_paused_keeps_active_frozen():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=2)
    m.on_step_start(0.0, "A", "B")
    m.pause(1.0)
    m.on_step_start(2.0, "B", "-")   # new step begins while paused
    # new step's active must not run until resume
    assert m.step_clock.active(4.0) == 0.0
    assert m.step_clock.elapsed(4.0) == 2.0
    m.resume(4.0)
    assert m.step_clock.active(5.0) == 1.0


def test_repetition_and_rep_chain():
    m = ProtocolStatusModel()
    m.on_repetition(1, 3)
    assert m.repeats_completed == 1
    assert m.repeats_total == 3
    m.set_rep_chain("rep 2/3 of 'Wash'")
    assert m.rep_chain_label == "rep 2/3 of 'Wash'"


def test_stop_freezes_all_and_clears_running():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, "A", "-")
    m.stop(3.0)
    assert m.running is False
    assert m.protocol_clock.elapsed(99.0) == 3.0
    assert m.step_clock.elapsed(99.0) == 3.0


def test_reset_restores_defaults():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=5)
    m.on_step_start(0.0, "A", "B")
    m.reset()
    assert m.step_index == 0
    assert m.step_total == 0
    assert m.recent_step_name == "-"
    assert m.running is False
    assert m.protocol_clock.elapsed(9.0) == 0.0


def test_observers_fire_on_counter_change():
    m = ProtocolStatusModel()
    seen = []
    m.observe(lambda e: seen.append(e.new), "step_index")
    m.on_protocol_start(0.0, 2)
    m.on_step_start(0.0, "A", "B")
    assert 1 in seen
