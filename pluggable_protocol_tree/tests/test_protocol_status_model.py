"""Unit tests for ProtocolStatusModel (pure, fake-clock, no Qt)."""
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel


def test_protocol_start_sets_total_and_runs():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=3)
    assert m.step_total == 3
    assert m.step_index == 0
    assert m.running is True
    assert m.protocol_clock.elapsed(2.0) == 2.0


def test_step_start_sets_position_and_resets_phase():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=3)
    m.on_step_start(0.0, 1, 3, (0,), "Step A", "Step B")
    assert m.step_index == 1
    assert m.step_total == 3
    assert m.current_step_path == (0,)
    assert m.recent_step_name == "Step A"
    assert m.next_step_name == "Step B"
    assert m.phase_index == 0
    assert m.phase_total == 0
    assert m.step_clock.elapsed(1.0) == 1.0
    m.on_step_start(1.0, 2, 3, (1,), "Step B", "-")
    assert m.step_index == 2
    assert m.current_step_path == (1,)
    # step clock restarted at t=1.0
    assert m.step_clock.elapsed(3.0) == 2.0


def test_phase_start_sets_counts_and_target():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, 1, 1, (0,), "A", "-")
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
    m.on_step_start(0.0, 1, 1, (0,), "A", "-")
    m.on_phase_start(0.0, 1, 1, 1.0)
    m.pause(1.0)
    assert m.paused is True
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
    m.on_step_start(0.0, 1, 2, (0,), "A", "B")
    m.pause(1.0)
    m.on_step_start(2.0, 2, 2, (1,), "B", "-")   # new step begins while paused
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


def test_reset_restores_defaults_and_zeroes_clocks():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=5)
    m.on_step_start(0.0, 1, 5, (0,), "A", "B")
    m.reset()
    assert m.step_index == 0
    assert m.step_total == 0
    assert m.current_step_path is None
    assert m.recent_step_name == "-"
    assert m.running is False
    assert m.protocol_clock.elapsed(9.0) == 0.0
    assert m.step_clock.elapsed(9.0) == 0.0
    assert m.phase_clock.elapsed(9.0) == 0.0


def test_observers_fire_on_counter_change():
    m = ProtocolStatusModel()
    seen = []
    m.observe(lambda e: seen.append(e.new), "step_index")
    m.on_protocol_start(0.0, 2)
    m.on_step_start(0.0, 1, 2, (0,), "A", "B")
    assert 1 in seen


def test_current_step_path_observable():
    m = ProtocolStatusModel()
    seen = []
    m.observe(lambda e: seen.append(e.new), "current_step_path")
    m.on_protocol_start(0.0, 2)
    m.on_step_start(0.0, 1, 2, (0,), "A", "B")
    assert (0,) in seen


def test_seek_step_sets_index_and_resets_step_timer_frozen_while_paused():
    m = ProtocolStatusModel()
    m.on_protocol_start(now=0.0, step_total=5)
    m.on_step_start(0.0, 1, 5, (0,), "A", "B")
    m.on_step_start(1.0, 2, 5, (1,), "B", "C")
    m.pause(now=2.0)
    m.seek_step(2.0, 4, 5, (3,), "D", "E")
    assert m.step_index == 4                      # set, not incremented
    assert m.current_step_path == (3,)
    assert m.recent_step_name == "D"
    assert m.phase_index == 0 and m.phase_total == 0
    assert m.step_clock.elapsed(now=9.0) == 0.0
    assert m.step_clock.active(now=9.0) == 0.0


def test_seek_phase_resets_phase_timer_frozen_while_paused():
    m = ProtocolStatusModel()
    m.on_protocol_start(now=0.0, step_total=1)
    m.on_step_start(0.0, 1, 1, (0,), "A", "-")
    m.on_phase_start(now=0.0, phase_index=1, phase_total=4, phase_target_s=2.0)
    m.pause(now=1.0)
    m.seek_phase(now=1.0, phase_index=3, phase_total=4, phase_target_s=2.0)
    assert m.phase_index == 3 and m.phase_total == 4
    assert m.phase_clock.elapsed(now=9.0) == 0.0
    assert m.phase_clock.active(now=9.0) == 0.0


def test_seek_then_step_report_does_not_drift_index():
    """Bug #471: after a seek to step k while paused, the executor's
    step_started for that frame SETS (not increments) -- the index stays at k,
    no '10/9' drift."""
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=9)
    m.on_step_start(0.0, 1, 9, (0,), "s1", "s2")
    m.on_step_start(1.0, 2, 9, (1,), "s2", "s3")   # at step 2
    m.pause(2.0)
    m.seek_step(2.0, 5, 9, (4,), "s5", "s6")        # navigate to step 5
    assert m.step_index == 5
    m.resume(2.0)
    m.on_step_start(2.0, 5, 9, (4,), "s5", "s6")     # executor re-reports frame 5
    assert m.step_index == 5                         # NOT 6
    m.on_step_start(3.0, 6, 9, (5,), "s6", "s7")
    assert m.step_index == 6                         # advances normally
    assert m.step_index <= m.step_total             # never exceeds total


def test_on_dyn_phase_sets_unique_phase_plus_idle_total():
    m = ProtocolStatusModel()
    m.on_dyn_phase(now=0.0, cycle_pos=2, cycle_len=4, phase_target_s=2.0)
    assert m.phase_index == 2
    assert m.phase_total == 5          # 4 unique + 1 idle cell
    assert m.dyn_idle is False


def test_on_dyn_idle_parks_on_idle_cell():
    m = ProtocolStatusModel()
    m.on_dyn_idle(now=0.0, cycle_len=4)
    assert m.phase_index == 5          # idle cell is the last (1-based)
    assert m.phase_total == 5
    assert m.dyn_idle is True


def test_reset_clears_dyn_idle():
    m = ProtocolStatusModel()
    m.on_dyn_idle(now=0.0, cycle_len=4)
    m.reset()
    assert m.dyn_idle is False
