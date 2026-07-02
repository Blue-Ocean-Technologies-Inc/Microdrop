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


def test_ack_wait_freezes_active_without_entering_paused():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, 1, 1, (0,), "A", "-")
    m.on_phase_start(0.0, 1, 1, 1.0)
    m.enter_ack_wait(1.0)
    # An ack-wait is a pause for timing only: active freezes, elapsed keeps
    # ticking, and the operator-Paused flag is NOT set.
    assert m.paused is False
    assert m.protocol_clock.elapsed(5.0) == 5.0
    assert m.protocol_clock.active(5.0) == 1.0
    assert m.step_clock.active(5.0) == 1.0
    assert m.phase_clock.active(5.0) == 1.0
    m.exit_ack_wait(5.0)
    assert m.phase_clock.active(6.0) == 2.0


def test_nested_ack_waits_thaw_only_when_last_ends():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, 1, 1, (0,), "A", "-")
    m.on_phase_start(0.0, 1, 1, 1.0)
    m.enter_ack_wait(1.0)          # depth 1 -> freeze
    m.enter_ack_wait(2.0)          # depth 2 -> already frozen
    m.exit_ack_wait(3.0)          # depth 1 -> still frozen
    assert m.phase_clock.active(4.0) == 1.0
    m.exit_ack_wait(4.0)          # depth 0 -> thaw
    assert m.phase_clock.active(5.0) == 2.0


def test_ack_wait_ending_while_operator_paused_stays_frozen():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, 1, 1, (0,), "A", "-")
    m.on_phase_start(0.0, 1, 1, 1.0)
    m.enter_ack_wait(1.0)          # freeze via wait
    m.pause(2.0)                   # operator also pauses (already frozen)
    m.exit_ack_wait(3.0)          # wait ends but operator still paused
    assert m.paused is True
    assert m.phase_clock.active(9.0) == 1.0   # stays frozen
    m.resume(9.0)
    assert m.phase_clock.active(10.0) == 2.0


def test_phase_start_during_ack_wait_starts_frozen():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, 1, 1, (0,), "A", "-")
    m.enter_ack_wait(0.0)                 # wait in flight before the phase
    m.on_phase_start(1.0, 1, 1, 1.0)     # phase clock starts, must be frozen
    assert m.phase_clock.active(5.0) == 0.0
    m.exit_ack_wait(5.0)
    assert m.phase_clock.active(6.0) == 1.0


def test_ack_wait_ending_after_paused_seek_does_not_start_sought_clocks():
    # Seek-stopped clocks may only be fresh-started by an operator resume.
    # An exit_ack_wait thaw must leave them at 0 until the executor's
    # step_started re-seats them — the sought-to step has not begun executing.
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=2)
    m.on_step_start(0.0, 1, 2, (0,), "A", "B")
    m.enter_ack_wait(1.0)                 # step A blocks on an ack
    m.pause(2.0)                          # operator pauses during the wait
    m.seek_step(3.0, 2, 2, (1,), "B", "-")
    m.resume(4.0)                         # wait still in flight: stay frozen
    m.exit_ack_wait(5.0)                  # thaws protocol clock ONLY
    assert m.step_clock.active(9.0) == 0.0
    assert m.step_clock.elapsed(9.0) == 0.0
    assert m.protocol_clock.active(9.0) == 5.0   # frozen 1.0-5.0, then resumed
    m.on_step_start(9.0, 2, 2, (1,), "B", "-")   # executor re-seats the clock
    assert m.step_clock.active(10.0) == 1.0


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
    assert m.dyn_loop_active is True   # (#477) flags the live dynamic loop


def test_on_dyn_idle_parks_on_idle_cell():
    m = ProtocolStatusModel()
    m.on_dyn_idle(now=0.0, cycle_len=4)
    assert m.phase_index == 5          # idle cell is the last (1-based)
    assert m.phase_total == 5
    assert m.dyn_idle is True
    assert m.dyn_loop_active is True   # idle cell is still mid-dynamic-loop


def test_step_start_clears_stale_dyn_loop_state():
    """Bug #477: advancing to the next step must drop the previous step's
    dynamic-loop state, or a normal step inherits a stale idle cell."""
    m = ProtocolStatusModel()
    m.on_dyn_phase(now=0.0, cycle_pos=2, cycle_len=4, phase_target_s=2.0)
    assert m.dyn_loop_active is True
    m.on_step_start(1.0, 2, 3, (1,), "Step B", "Step C")
    assert m.dyn_idle is False
    assert m.dyn_loop_active is False


def test_normal_phase_clears_dyn_loop_active():
    m = ProtocolStatusModel()
    m.on_dyn_phase(now=0.0, cycle_pos=2, cycle_len=4, phase_target_s=2.0)
    assert m.dyn_loop_active is True
    m.on_phase_start(now=1.0, phase_index=1, phase_total=2, phase_target_s=1.0)
    assert m.dyn_loop_active is False
    assert m.dyn_idle is False


def test_seek_step_clears_dyn_loop_active():
    m = ProtocolStatusModel()
    m.on_dyn_idle(now=0.0, cycle_len=4)
    assert m.dyn_loop_active is True
    m.seek_step(1.0, 4, 5, (3,), "D", "E")
    assert m.dyn_idle is False
    assert m.dyn_loop_active is False


def test_reset_clears_dyn_idle():
    m = ProtocolStatusModel()
    m.on_dyn_idle(now=0.0, cycle_len=4)
    m.reset()
    assert m.dyn_idle is False
    assert m.dyn_loop_active is False
