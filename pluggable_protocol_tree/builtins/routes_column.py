"""Routes column + RoutesHandler.

Per-step list of routes (each route = ordered list of electrode IDs).
Cell shows a read-only summary; the demo's SimpleDeviceViewer is the
primary edit path in PPT-3.

The RoutesHandler walks iter_phases() over the row's electrodes /
routes / trail config. For each phase it does TWO things, in the same
order the legacy protocol_grid did them:

  1. **Display**: publishes ``PROTOCOL_TREE_DISPLAY_STATE`` to the
     device viewer with the phase's electrode IDs. Synchronous, no
     ack — the DV's overlay updates immediately. This always fires,
     including in preview mode.
  2. **Hardware**: only when ``preview_mode`` is False, publishes
     ``ELECTRODES_STATE_CHANGE`` (the hardware-actuation topic) and
     blocks via ``ctx.wait_for(ELECTRODES_STATE_APPLIED)`` for the
     dropbot's ack. Acts as backpressure so we don't flood the
     hardware queue.

The hardware-side consumer (dropbot_controller) does NOT know about
preview mode — preview gating happens entirely on the sender side, by
not publishing the hardware message at all. Matches the legacy split
in protocol_grid/services/protocol_runner_controller.py:_execute_next_phase.

Priority 30 keeps this in a strictly earlier bucket than
DurationColumnHandler (90), so the duration sleep only starts after
ALL phases have completed and been ack'd.
"""

import logging
import time

from pyface.qt.QtCore import Qt
from traits.api import List, Str

from electrode_controller.consts import electrode_state_change_publisher
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODE_TO_CHANNEL_KEY,
    ELECTRODES_STATE_APPLIED,
    PROTOCOL_TREE_DISPLAY_STATE,
)
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)
from pluggable_protocol_tree.services.phase_math import (
    another_loop_fits, duration_loop_parts, iter_phases, loop_completion_fits,
)
from pluggable_protocol_tree.views.columns.base import BaseColumnView
from microdrop_application.dialogs.pyface_wrapper import confirm, YES, NO


logger = logging.getLogger(__name__)

# Sentinel set on ctx.scratch by RoutesHandler so DurationColumnHandler
# (priority 90) knows the per-phase dwells have already covered the
# row's total duration and shouldn't be slept again.
DURATION_CONSUMED_KEY = "_routes_consumed_duration"

# Generic opt-in hook (set on ctx.scratch in on_pre_step by any column that
# wants this step's phases held open for buffering). When present,
# RoutesHandler gives each phase a post-dwell grace + honours
# add_time_buffer_to_current_phase, and in duration mode loops the unit cycle
# within the budget. This keeps RoutesHandler decoupled — it never names the
# columns that hook in (same pattern as DURATION_CONSUMED_KEY above).
# volume_threshold sets this; other columns may too.
PHASE_HOLD_REQUESTED_KEY = "_phase_hold_requested"

# Cooperative-sleep slice: how often to check stop_event during a
# per-phase dwell so a Stop press lands within ~50ms even on long
# durations.
_SLICE_S = 0.05

# Post-dwell grace: when a step holds the phase for sibling columns (e.g.
# volume threshold), how long to wait past the nominal dwell for one of
# them to register buffer / open a dialog before advancing anyway. Covers
# the tiny gap between the dwell ending and a sibling detecting the miss,
# so a participating column isn't missed and a non-participating one never
# deadlocks. While the run is paused (operator dialog up) the grace is
# refreshed each loop, so a slow operator never causes an early advance.
_HOLD_GRACE_S = 0.5

# Indirection so the dynamic duration loop's wall-clock reads can be
# replaced with a deterministic fake clock in tests. Production uses
# time.monotonic unchanged.
_monotonic = time.monotonic


def dyn_resume_start(cursor_phase_index: int, cycle_len: int):
    """Resolve a paused-seek cursor phase to a dynamic-loop start.

    Returns (start_phase_in_cycle, start_idle). cursor_phase_index is the
    0-based unique-phase the operator toggled to; an index at/over cycle_len
    is the trailing idle cell. Negative clamps to phase 0 (#477)."""
    if cycle_len <= 0:
        return 0, False
    if cursor_phase_index >= cycle_len:
        return 0, True
    return max(0, int(cursor_phase_index)), False


def _confirm_finish_loop_over_budget():
    """Operator prompt when a seek-resume lands partway through a loop that
    can no longer finish within the route-rep budget (#477). Returns True to
    finish the loop and advance, False to leave the run paused."""
    from microdrop_application.dialogs.pyface_wrapper import confirm, YES
    return confirm(
        None,
        "The set route-rep time is up, but the current loop is not back at its "
        "start position. Finish this loop (electrodes return to start) and then "
        "move to the next step?",
        title="Loop needs more time",
        cancel=False,
    ) == YES


def _prompt_time_expired():
    """Operator prompt when the route-rep duration expires before the step has
    finished and the electrodes are NOT back at their start position (#477
    follow-up). Three choices, returned as a string:

      'finish' -> run the rest (complete the loop / remaining phases) so the
                  electrodes return to start, then advance to the next step,
      'next'   -> skip the rest of this step and advance to the next step now,
      'paused' -> stay paused on this step so the operator decides.
    """
    result = confirm(
        None,
        "The route-rep duration time has expired, but this step has not "
        "finished and the electrodes are not back at their start position.<br><br>"
        "What would you like to do?<br><br>"
        "<b> Pause </b> and decide next step manually; <br><br>"
        "<b> Skip </b> to next step; <br> <br>"
        "<b> Complete </b>: Complete rest of loop then proceed to next step. <br><br>",
        title="Route-rep time expired",
        cancel=True,
        yes_label="Complete",
        no_label="Skip",
        cancel_label="Pause",
    )
    if result == YES:
        return "finish"
    if result == NO:
        return "next"
    return "paused"


class RoutesColumnModel(BaseColumnModel):
    """List[List[str]] trait. Default = empty list."""
    def trait_for_row(self):
        return List(List(Str), value=list(self.default_value or []),
                    desc="Per-step list of routes; each route is an "
                         "ordered list of electrode IDs.")


class RoutesSummaryView(BaseColumnView):
    """Read-only cell. '0' / '1' / 'N'."""

    def format_display(self, value, row):
        return str(len(value or []))

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def create_editor(self, parent, context):
        return None


class RoutesHandler(BaseColumnHandler):
    """Drives electrode actuation for the step. See module docstring.

    The row's ``duration_s`` is the dwell time PER PHASE. Each phase
    actuates for ``duration_s`` seconds before transitioning to the
    next; this matches the legacy protocol_grid where each protocol
    row was a single phase. After the last phase, RoutesHandler marks
    the per-step duration as consumed via ``ctx.scratch`` so the
    DurationColumnHandler at priority 90 doesn't dwell a second time.
    """
    priority = 30
    wait_for_topics = [ELECTRODES_STATE_APPLIED]
    # Provider default for the Protocol Settings ack-wait grid: 5.0s of
    # headroom for cold-broker first-publish (~1-2s); typical ack <100ms.
    default_ack_time_s = 5.0

    def _run_phase(self, phase, *, ctx, mapping, static_routes, step_uuid,
                   step_label, preview_mode, per_phase_dwell, stop_event,
                   pause_event, signals, phase_index, phase_total,
                   hold_for_buffer=False, honor_pause=True,
                   emit_phase_started=True, time_expired=None):
        """Run ONE phase: clear the early-advance event, honour stop/pause,
        publish display (+ hardware when not preview), wait the ack, and
        dwell (cut short by phase_advance_event). Returns False if a Stop
        landed before/at this phase (caller should break its loop), True
        otherwise.

        ``phase_total`` is 0 for the dynamic loop (total unknown while
        looping); callers in the static path pass the materialized count.

        ``hold_for_buffer``: when True, after the nominal dwell give sibling
        columns a grace window to extend THIS phase (see the post-dwell hold
        below). Used for volume-threshold steps so a missed threshold can
        hold the phase open rather than advancing on schedule.

        ``emit_phase_started``: the dynamic duration loop already emits its own
        ``dyn_phase_started`` (which drives the model AND sets dyn_loop_active);
        it passes False here so the generic ``phase_started`` — whose handler
        clears dyn_loop_active — doesn't immediately undo that flag (#477).

        ``time_expired`` (optional zero-arg predicate): polled each slice during
        the dwell AND the post-dwell hold; when it returns True the phase ends
        at once. The dynamic duration loop passes it so a phase held open by
        volume threshold (a stuck droplet) still yields the instant the rep-
        duration budget is crossed, letting the caller raise the overrun prompt
        rather than waiting for the hold to end on its own (#477 follow-up).
        """
        # Fresh slate: a handler set in phase N-1 must NOT carry over into
        # phase N. Cleared before the stop/pause checks so a stale set
        # doesn't accidentally fire here. Same for any unconsumed phase-time
        # buffer left over from a phase that ended early.
        ctx.phase_advance_event.clear()
        ctx.reset_phase_time_buffer()
        # A pending mid-run seek (operator navigated away while paused) must
        # cut this phase's dwell/hold short on resume so the leftover time
        # doesn't run before the executor redirects (#471).
        def _seek_pending():
            return ctx.protocol.cursor.resume_target is not None
        if stop_event.is_set():
            return False
        # Pause check at the phase boundary — block here so the
        # next phase's actuation doesn't fire until the user
        # resumes. The executor's between-step pause check
        # doesn't reach inside on_step's phase loop, so without
        # this the routes keep playing through a Pause click.
        if honor_pause and pause_event.is_set():
            pause_event.wait_cleared()
            if stop_event.is_set():
                return False

        # Phase wall-clock origin: used to cap the post-dwell automatic grace
        # so a single phase's nominal dwell + grace never exceeds
        # per_phase_dwell, keeping worst_loop = cycle_len * per_phase_dwell a
        # TRUE upper bound for the dynamic duration loop (#477 §10). Deliberate
        # operator holds (pause / buffer extension) refresh past this cap and
        # are credited back to the budget separately — they are not bounded here.
        phase_start = time.monotonic()

        electrodes = sorted(phase)
        channels = sorted(mapping[e] for e in electrodes if e in mapping)
        for e in electrodes:
            if e not in mapping:
                logger.warning(
                    f"electrode {e!r} has no channel mapping; "
                    f"actuation channel skipped"
                )

        if signals is not None and emit_phase_started:
            signals.phase_started = (
                phase_index, phase_total, per_phase_dwell,
            )

        # 1. Display: synchronous, no ack. editable tracks Advanced Mode so
        # the operator can edit the running step in the device viewer (#434);
        # the echo-back of our own actuation is prevented on the DV side
        # (publish_electrode_update ignores apply-time mutations), not by
        # forcing editable False.
        display_msg = ProtocolTreeDisplayMessage(
            electrodes=electrodes,
            routes=static_routes,
            step_id=step_uuid,
            step_label=step_label,
            free_mode=False,
            editable=bool(getattr(ctx.protocol, "advanced_mode", False)),
        )
        publish_message(
            topic=PROTOCOL_TREE_DISPLAY_STATE,
            message=display_msg.serialize(),
        )

        # 2. Hardware: only when not preview. dropbot_controller
        # has no preview-mode awareness — gating happens here, on
        # the sender side, by simply not publishing.
        if not preview_mode:
            electrode_state_change_publisher.publish(actuated_channels=channels)
            # Ack wait from the Protocol Settings grid (resolved per
            # phase so mid-run Settings edits apply); 0 = fire-and-
            # forget. In preview we skip the publish + wait entirely so
            # the user gets a snappy visual playback with no per-phase
            # stalls.
            if self.ack_time_s > 0:
                ctx.wait_for(ELECTRODES_STATE_APPLIED, timeout=self.ack_time_s)

        _cooperative_sleep(per_phase_dwell, stop_event, pause_event,
                           phase_advance_event=ctx.phase_advance_event,
                           seek_pending=_seek_pending,
                           time_expired=time_expired)

        # Consume any phase-time buffer a sibling column added (only relevant
        # when this step opted into holding — see below) and tell the status
        # bar so its target grows to match. Whether the held time is credited
        # back to a duration budget is the requesting column's policy (it calls
        # ctx.note_phase_extension), not RoutesHandler's — we only hold + report.
        def _take_and_emit():
            extra = ctx.take_phase_time_buffer()
            if extra > 0 and signals is not None:
                signals.phase_extended = extra
            return extra

        # Post-dwell hold: a sibling column (e.g. volume threshold) often
        # only detects a miss right at the dwell's end — too late to have
        # added buffer mid-dwell. Give it a short grace to register buffer
        # or open a dialog (which pauses us), holding THIS phase's actuation
        # meanwhile. phase_advance_event (threshold reached / operator
        # "proceed") ends the hold at once; the grace bounds it so a step
        # whose sibling never participates can't deadlock. While paused
        # (dialog up) we refresh the grace each loop so a deliberate operator
        # never triggers an early advance.
        if hold_for_buffer and not preview_mode:
            # Cap the AUTOMATIC grace so dwell + grace <= per_phase_dwell: the
            # threshold timeout equals the duration-column value, so a phase
            # that never reaches threshold must still end by per_phase_dwell
            # (#477 §10). Once the dwell has already consumed per_phase_dwell,
            # this cap is the phase start + dwell <= now, so the loop breaks at
            # once and adds nothing. A non-zero gap (e.g. the dwell ended early
            # on a stale advance) still gets the bounded grace. Deliberate
            # operator holds below (pause / buffer) refresh past this cap.
            grace_deadline = min(time.monotonic() + _HOLD_GRACE_S,
                                 phase_start + per_phase_dwell)
            while (not stop_event.is_set()
                   and not ctx.phase_advance_event.is_set()):
                if _seek_pending():
                    break
                # Rep-duration budget crossed while holding (e.g. a stuck
                # droplet held open by volume threshold): stop holding so the
                # caller can raise the overrun prompt (#477 follow-up).
                if time_expired is not None and time_expired():
                    break
                if pause_event.is_set():
                    # Poll so a budget expiry DURING the hold-pause wakes us;
                    # the top-of-loop time_expired check then breaks the hold so
                    # the caller can raise the overrun prompt while paused.
                    _wait_through_pause(pause_event, stop_event, time_expired)
                    grace_deadline = time.monotonic() + _HOLD_GRACE_S
                    continue
                extra = _take_and_emit()
                if extra > 0:
                    _cooperative_sleep(
                        extra, stop_event, pause_event,
                        phase_advance_event=ctx.phase_advance_event,
                        buffer_provider=_take_and_emit,
                        seek_pending=_seek_pending,
                        time_expired=time_expired)
                    grace_deadline = time.monotonic() + _HOLD_GRACE_S
                    continue
                if time.monotonic() >= grace_deadline:
                    break
                time.sleep(_SLICE_S)
        return True

    def _run_dynamic_duration_loop(self, row, *, ctx, mapping, static_routes,
                                   step_uuid, step_label, preview_mode,
                                   per_phase_dwell, stop_event, pause_event,
                                   signals, budget):
        """Duration mode + a phase-hold hook: run full unit cycles while a
        guaranteed FULL loop still fits the RAW wall-clock budget, then enter
        an explicit idle phase (electrodes off) until the budget elapses.

        Budget accounting is RAW wall-clock since step start (#477): pauses
        and holds count against the budget — there is no extension credit-back.
        At each loop boundary ``another_loop_fits`` gates whether one more
        worst-case loop (every phase at ``per_phase_dwell``) finishes in time;
        when it won't, the loop closes back at the unit-cycle start and idles.
        Because every loop ends at phase 0, there is no separate return phase —
        the next loop's phase 0 IS the return.

        A hook column (e.g. volume threshold) cuts each phase short via
        phase_advance_event, so wall-clock elapses slower than
        ``per_phase_dwell`` predicts and more loops fit. The phase index is a
        running counter with total 0 (unknown while looping) so the status bar
        shows the advancing phase number.

        Seek re-entry: on a paused seek the cursor's phase resolves via
        ``dyn_resume_start`` to a start phase or the idle cell. If the seek
        lands partway through a loop that can no longer finish in budget, the
        operator is prompted (``_confirm_finish_loop_over_budget``): YES runs
        the partial loop to its end then advances; NO pauses."""
        # return_phase is unused now: every loop closes back at the unit-cycle
        # start (the next loop's phase 0 IS the return), and idle replaces the
        # old soft-end remainder (#477).
        ramp_up, unit_cycle, _return_phase = duration_loop_parts(
            static_electrodes=list(getattr(row, "electrodes", []) or []),
            routes=list(getattr(row, "routes", []) or []),
            trail_length=int(getattr(row, "trail_length", 1)),
            trail_overlay=int(getattr(row, "trail_overlay", 0)),
            soft_start=bool(getattr(row, "soft_start", False)),
        )
        # No routes -> unit_cycle is the single static phase and return_phase
        # is None; the loop below repeats that static actuation across the
        # budget (holding the droplet, re-checking the threshold each dwell)
        # rather than yielding it once. Intentional for VT static-merge steps.
        # cycle_len phases at per_phase_dwell each = one worst-case loop; the
        # guaranteed-loop gate (another_loop_fits) computes that bound itself.
        cycle_len = len(unit_cycle)
        step_start = _monotonic()
        running_idx = 0
        # Set once the time-expired prompt has been shown for this step (or the
        # operator chose to finish the loop): it both suppresses re-prompting and
        # disables the mid-phase budget wake, so the loop-completion phases dwell
        # NORMALLY (the droplet must physically return to start) instead of
        # strobing once we are knowingly over budget.
        overrun_prompted = False

        def raw_elapsed():
            # RAW wall-clock since step start: pauses and holds count against
            # the budget (NOT pause-aware, NOT extension-credited) — #477.
            return _monotonic() - step_start

        # Resolve the resume phase (#477 review fix). A SAME-STEP seek leaves
        # cursor.phase_index at 0 — the real target lives in resume_target,
        # recovered via decision_at_phase exactly like the static phase loop.
        # A DIFFERENT-STEP seek is pre-resolved by the executor into
        # cursor.phase_index with resume_target already cleared. A fresh entry
        # is phase_index 0 with no resume_target.
        cursor = ctx.protocol.cursor
        if cursor.resume_target is not None:
            action, target_phase = cursor.decision_at_phase(0)
            if action == "abort":
                # Different step/frame: unwind so the executor's frame walk
                # re-enters the correct target.
                ctx.step_phases_done_event.set()
                return
            # ("jump", target_phase): same-step seek — consume it here.
            seek_phase = int(target_phase)
            came_from_seek = True
            cursor.clear_seek()
        else:
            seek_phase = int(cursor.phase_index)
            came_from_seek = seek_phase > 0
        _, start_idle = dyn_resume_start(seek_phase, cycle_len)

        def _run_cycle_phase(phase, cycle_pos, guard_budget=False):
            nonlocal running_idx
            running_idx += 1
            if signals is not None:
                signals.dyn_phase_started = (cycle_pos + 1, cycle_len,
                                             per_phase_dwell)
            # guard_budget: only the main active-loop phases pass True. It wakes
            # the dwell/hold the instant the RAW budget is crossed (within a
            # slice) so the overrun prompt fires even while a phase is held open
            # by volume threshold (a stuck droplet). Gated on not-yet-prompted so
            # the loop-completion phases (post-prompt) dwell normally. The
            # ramp-up and seek-resume finishes pass False (never break early).
            time_expired = (
                (lambda: not overrun_prompted and raw_elapsed() >= budget)
                if (guard_budget and budget > 0) else None)
            # hold_for_buffer=True: this loop only runs when a column requested
            # the phase-hold hook, so honour the same post-dwell hold/dialog as
            # the static path. honor_pause=False: this loop owns the pause/seek
            # checkpoints (the executor re-enters the step on a seek).
            return self._run_phase(
                phase, ctx=ctx, mapping=mapping, static_routes=static_routes,
                step_uuid=step_uuid, step_label=step_label,
                preview_mode=preview_mode, per_phase_dwell=per_phase_dwell,
                stop_event=stop_event, pause_event=pause_event,
                signals=signals, phase_index=cycle_pos + 1,
                phase_total=cycle_len + 1, hold_for_buffer=True,
                honor_pause=False, emit_phase_started=False,
                time_expired=time_expired)

        def _go_idle():
            # Explicit idle: electrodes off once, then hold to the budget. A
            # seek (operator toggled away from idle) returns so the executor's
            # pause/seek path re-enters this step.
            idle_for = max(0.0, budget - raw_elapsed())
            logger.info(
                f"[dyn-loop] entering IDLE (electrodes off): elapsed="
                f"{raw_elapsed():.2f}s of rep-duration budget {budget:.2f}s "
                f"-> idle for ~{idle_for:.2f}s until the budget elapses")
            if not preview_mode:
                electrode_state_change_publisher.publish(actuated_channels=[])
            if signals is not None:
                signals.dyn_idle_entered = cycle_len
            while not stop_event.is_set() and raw_elapsed() < budget:
                if cursor.resume_target is not None:
                    return
                _cooperative_sleep(
                    min(0.1, budget - raw_elapsed()), stop_event, pause_event,
                    seek_pending=lambda: cursor.resume_target is not None)

        def _resume_at(target):
            """Resolve a (just-cleared) same-step seek to phase ``target`` to
            the loop index to run from, or None when the step finishes here.

            ``target`` >= cycle_len is the idle cell -> idle to the budget. A
            mid-loop target that can no longer finish within the budget prompts
            the operator (finish-then-advance vs stay paused) — the same rule a
            fresh seek-resume uses. A fresh non-seek entry passes 0 and just
            runs from the loop start."""
            k = max(0, int(target))
            if k >= cycle_len:
                _go_idle()
                return None
            if k > 0 and not loop_completion_fits(
                    raw_elapsed(), k, cycle_len, per_phase_dwell, budget):
                if ctx.prompt_gui(lambda: _confirm_finish_loop_over_budget()):
                    # Finish this loop (back to start), then advance.
                    for j in range(k, cycle_len):
                        if not _run_cycle_phase(unit_cycle[j], j):
                            return None
                    ctx.step_phases_done_event.set()
                    return None
                # Declined: stay paused on this step at k. A plain resume runs
                # from k; a re-toggle is picked up by the loop's seek checkpoint.
                ctx.protocol.pause()
            return k

        # Soft-start ramp only on a fresh (non-seek) entry that isn't idle.
        if not came_from_seek and not start_idle:
            for phase in ramp_up:
                if not _run_cycle_phase(phase, 0):
                    return

        # Resolve the entry position (idle / over-budget prompt / run-from-k);
        # for a fresh entry this is just phase 0.
        i = _resume_at(seek_phase)
        if i is None:
            return

        # Run full unit cycles while another guaranteed loop still fits. The
        # in-loop pause + seek checkpoint repositions a mid-loop toggle IN PLACE
        # (mirrors the static phase loop): without it a pending seek would leave
        # resume_target stuck, collapsing every remaining dwell to ~0 (strobing
        # the rest of the cycle) and skipping idle, so the step would race to
        # the next one (#477).
        while not stop_event.is_set():
            while i < cycle_len:
                if pause_event.is_set():
                    # Poll the budget so an expiry during a between-phase pause
                    # is noticed: on wake the next phase's dwell breaks at once
                    # (over budget) and the post-phase overrun check prompts.
                    _wait_through_pause(
                        pause_event, stop_event,
                        lambda: not overrun_prompted and raw_elapsed() >= budget)
                    if stop_event.is_set():
                        return
                if cursor.resume_target is not None:
                    action, target_phase = cursor.decision_at_phase(i)
                    if action == "abort":
                        # Different step: unwind; the executor re-enters the
                        # target step (leave resume_target set).
                        ctx.step_phases_done_event.set()
                        return
                    cursor.clear_seek()
                    i = _resume_at(int(target_phase))
                    if i is None:
                        return
                    continue
                if not _run_cycle_phase(unit_cycle[i], i, guard_budget=True):
                    return
                i += 1
                # Overrun guard (#477 follow-up): the rep-duration budget ran
                # out MID-loop (electrodes not back at start) — e.g. a phase
                # held past its dwell, or the budget was too short for even one
                # full loop (the first loop runs unconditionally). Ask the
                # operator once per step what to do. Skipped in preview (a
                # visual dry-run shouldn't block on a dialog).
                if (not preview_mode and not overrun_prompted and budget > 0
                        and i < cycle_len and raw_elapsed() >= budget):
                    overrun_prompted = True
                    decision = ctx.prompt_gui(_prompt_time_expired) or "finish"
                    if decision == "next":
                        ctx.step_phases_done_event.set()
                        return
                    if decision == "paused":
                        ctx.protocol.pause()
                    # 'finish' (or an external resume): fall through and run the
                    # rest of the loop back to start; the loop gate below is now
                    # over budget, so the next stop is idle (which exits at once)
                    # then advance. No re-prompt — overrun_prompted stays set.
            i = 0
            elapsed = raw_elapsed()
            worst_loop = cycle_len * per_phase_dwell
            fits = per_phase_dwell > 0 and another_loop_fits(
                elapsed, cycle_len, per_phase_dwell, budget)
            # Explain the keep-looping-vs-idle decision so the operator can see
            # how the dynamic loop is spending the rep-duration budget (#477).
            logger.info(
                f"[dyn-loop] end of loop: elapsed={elapsed:.2f}s, "
                f"worst-case loop time={worst_loop:.2f}s "
                f"({cycle_len} phases x {per_phase_dwell:.2f}s), "
                f"available={max(0.0, budget - elapsed):.2f}s, "
                f"rep-duration budget={budget:.2f}s -> "
                f"{'run another loop' if fits else 'stop looping, go idle'}")
            if not fits:
                break
        if not stop_event.is_set():
            _go_idle()

    def on_step(self, row, ctx):
        mapping = ctx.protocol.scratch.get(ELECTRODE_TO_CHANNEL_KEY, {})
        per_phase_dwell = float(getattr(row, "duration_s", 0.0) or 0.0)
        stop_event = ctx.protocol.stop_event
        pause_event = ctx.protocol.pause_event
        preview_mode = bool(getattr(ctx.protocol, "preview_mode", False))

        # Cached per-step display message metadata. Routes stay
        # constant across phases — only the active-electrode set
        # changes per phase. step_label format matches the dotted-path
        # convention used elsewhere ("Step 1.2").
        step_uuid = getattr(row, "uuid", "") or ""
        step_label = f"Step {row.dotted_path()}"

        routes = list(getattr(row, "routes", []) or [])

        # Route Reps Dur mode is authoritative ONLY when the controls flag
        # says so. The same flag gates BOTH the duration-mode cycle
        # truncation below and the hold-pad after the loop — keeping them
        # in lockstep. In count mode (flag False) repeat_duration is just
        # a display estimate and must NOT truncate the loop, so we pass
        # repeat_duration_s=0 and let route_repetitions drive the cycles.
        in_duration_mode = (
            bool(getattr(row, "repeat_duration_controls", False))
            and float(getattr(row, "repeat_duration", 0.0) or 0.0) > 0
        )
        # Rep-duration budget (seconds); 0 in count mode. Shared by the dynamic
        # loop and the static path's overrun guard.
        budget = float(getattr(row, "repeat_duration", 0.0) or 0.0)

        signals = getattr(ctx.protocol, "signals", None)
        # Generic opt-in: a sibling column (e.g. volume threshold) requested in
        # on_pre_step that this step's phases be held open for buffering /
        # threshold-driven advancement. RoutesHandler honours the flag without
        # knowing which column set it — see PHASE_HOLD_REQUESTED_KEY.
        phase_hold = bool(ctx.scratch.get(PHASE_HOLD_REQUESTED_KEY, False))

        if in_duration_mode and phase_hold:
            self._run_dynamic_duration_loop(
                row, ctx=ctx, mapping=mapping, static_routes=routes,
                step_uuid=step_uuid, step_label=step_label,
                preview_mode=preview_mode, per_phase_dwell=per_phase_dwell,
                stop_event=stop_event, pause_event=pause_event,
                signals=signals, budget=budget)
        else:
            phases = list(iter_phases(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)),
                soft_end=bool(getattr(row, "soft_end", False)),
                repeat_duration_s=(float(getattr(row, "repeat_duration", 0.0))
                                   if in_duration_mode else 0.0),
                linear_repeats=bool(getattr(row, "linear_repeats", False)),
                n_repeats=int(getattr(row, "route_repetitions", 1)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
            cursor = ctx.protocol.cursor
            total_phases = len(phases)
            cursor.phase_total = total_phases
            # Begin at the cursor's phase (0 normally; the re-entry phase after
            # a different-step seek). Clamp into range.
            phase_i = max(0, min(int(cursor.phase_index), max(0, total_phases - 1)))
            seek_abort = False
            # Raw wall-clock origin for the duration-mode overrun guard below
            # (same RAW accounting as the dynamic loop: pauses/holds count).
            step_start = _monotonic()
            overrun_prompted = False
            skip_to_next = False
            # The loop-origin phase for the "complete loop" overrun choice: it
            # lets us stop as soon as the droplet is back at start instead of
            # running ALL the remaining predetermined reps (#477 follow-up).
            # Same origin the dynamic loop uses (zipped first window + static).
            _dlp_ramp, _dlp_cycle, _dlp_ret = duration_loop_parts(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)))
            start_set = _dlp_cycle[0] if _dlp_cycle else None
            finish_to_start = False
            # Budget-expiry predicate: lets a paused/dwelling phase wake the
            # instant the rep budget is crossed (so the prompt shows even while
            # paused). Disabled once prompted so the loop-completion phases dwell
            # normally. None in count mode (no budget).
            time_expired = (
                (lambda: not overrun_prompted
                 and (_monotonic() - step_start) >= budget)
                if (in_duration_mode and budget > 0) else None)
            while phase_i < total_phases:
                if stop_event.is_set():
                    break
                cursor.phase_index = phase_i
                # Pause checkpoint (this loop owns it; _run_phase is called with
                # honor_pause=False so it won't block again at its top). Poll the
                # budget so an expiry during a between-phase pause is noticed.
                if pause_event.is_set():
                    _wait_through_pause(pause_event, stop_event, time_expired)
                    if stop_event.is_set():
                        break
                # Honor a pending seek whenever one is set -- covers a pause that
                # landed HERE and one that landed mid-dwell (inside _run_phase)
                # then resumed (pause_event is already clear by now).
                if cursor.resume_target is not None:
                    action, target_phase = cursor.decision_at_phase(phase_i)
                    if action == "jump":          # same step -> jump in place
                        cursor.clear_seek()
                        phase_i = max(0, min(int(target_phase), total_phases - 1))
                        continue
                    if action == "abort":         # different step -> let the
                        seek_abort = True         # executor's frame walk redirect
                        break
                if not self._run_phase(
                        phases[phase_i], ctx=ctx, mapping=mapping,
                        static_routes=routes, step_uuid=step_uuid,
                        step_label=step_label, preview_mode=preview_mode,
                        per_phase_dwell=per_phase_dwell, stop_event=stop_event,
                        pause_event=pause_event, signals=signals,
                        phase_index=phase_i + 1, phase_total=total_phases,
                        hold_for_buffer=phase_hold, honor_pause=False,
                        time_expired=time_expired):
                    break
                phase_i += 1
                # "Complete loop" choice: stop the instant the droplet is back at
                # the loop origin — don't run the remaining predetermined reps.
                if (finish_to_start and start_set is not None
                        and phases[phase_i - 1] == start_set):
                    break
                # Overrun guard (#477 follow-up): duration mode with the budget
                # used up before the phases finished (e.g. the budget is shorter
                # than one full set of phases). Ask the operator once. Skipped in
                # preview (a visual dry-run shouldn't block on a dialog).
                # ``phase_i < total_phases - 1``: iter_phases appends a trailing
                # return-to-start phase, so when only THAT phase remains the step
                # is completing normally (it ends back at start) — not an
                # overrun. Only prompt while a real move phase still remains.
                if (in_duration_mode and not preview_mode and budget > 0
                        and not overrun_prompted and phase_i < total_phases - 1
                        and _monotonic() - step_start >= budget):
                    overrun_prompted = True
                    decision = ctx.prompt_gui(_prompt_time_expired) or "finish"
                    if decision == "next":
                        skip_to_next = True
                        break
                    if decision == "paused":
                        ctx.protocol.pause()
                    elif decision == "finish":
                        # Run only until the droplet is back at the loop origin,
                        # then advance — NOT all the remaining reps. If it is
                        # already there, advance now.
                        if start_set is not None and phases[phase_i - 1] == start_set:
                            skip_to_next = True
                            break
                        finish_to_start = True
            if seek_abort:
                # Leave resume_target set; the executor re-enters the target step.
                ctx.step_phases_done_event.set()
                return
            # Route Reps Dur mode: after the full cycles, hold the last
            # phase's electrodes (no new publish) for the exact leftover so
            # total step time lands on the budget precisely. Based on the
            # ACTUAL emitted phase count so it accounts for loop cycles,
            # ramps, and routes. Skipped when the budget already overran
            # (skip-to-next, or the operator let it finish past the budget).
            if (in_duration_mode and not stop_event.is_set()
                    and not overrun_prompted and not skip_to_next):
                pad = max(0.0, float(getattr(row, "repeat_duration", 0.0))
                              - len(phases) * per_phase_dwell)
                if pad > 0:
                    _cooperative_sleep(
                        pad, stop_event, pause_event,
                        seek_pending=lambda: cursor.resume_target is not None)

        # Tell DurationColumnHandler we already covered the dwell.
        ctx.scratch[DURATION_CONSUMED_KEY] = True
        # Signal sibling parallel-bucket handlers (e.g. VolumeThresholdHandler)
        # that the per-phase loop is done so they can exit their wait loops
        # cleanly. Without this, handlers blocked in
        # wait_for(ELECTRODES_STATE_CHANGE) for a next phase that will never
        # come would block the bucket's ThreadPoolExecutor indefinitely.
        ctx.step_phases_done_event.set()


def _wait_through_pause(pause_event, stop_event, time_expired=None) -> None:
    """Block while ``pause_event`` is set, polling each slice so a Stop or a
    rep-duration budget expiry (``time_expired``) is noticed DURING the pause
    rather than only when the operator resumes (#477 follow-up). Returns once
    unpaused, on stop, or on time_expired — the caller re-checks those. Does
    NOT itself clear the pause."""
    while pause_event is not None and pause_event.is_set():
        if pause_event.wait_cleared(timeout=_SLICE_S):
            return                       # resumed
        if stop_event.is_set() or (time_expired is not None and time_expired()):
            return                       # caller re-checks stop / budget


def _cooperative_sleep(seconds: float, stop_event, pause_event=None,
                       phase_advance_event=None, buffer_provider=None,
                       seek_pending=None, time_expired=None) -> None:
    """Sleep for ``seconds``, waking every _SLICE_S to check stop_event
    (and pause_event if provided). Used so a Stop or Pause press lands
    within ~50ms even mid-dwell. On pause: block in
    ``pause_event.wait_cleared()`` until the user resumes, then
    continue with the remaining dwell. Returns early on stop, on
    phase_advance_event (any handler can set it to cut the phase short),
    or when seconds reaches 0.

    ``buffer_provider`` (optional): a zero-arg callable polled each slice
    that returns seconds to ADD to the remaining dwell. Lets a sibling
    column extend the phase mid-dwell via
    ``StepContext.add_time_buffer_to_current_phase`` without restarting it.

    ``time_expired`` (optional): a zero-arg predicate polled each slice;
    returns early (cuts the dwell short) the first time it is True. Used by
    the dynamic duration loop to yield the instant the rep-duration budget
    is crossed, even mid-dwell/hold (#477 follow-up).
    """
    remaining = seconds
    while remaining > 0:
        if stop_event.is_set():
            return
        if phase_advance_event is not None and phase_advance_event.is_set():
            return
        # A seek requested while paused (operator navigated to another
        # step/phase) must abort the leftover dwell on resume — otherwise the
        # old step's remaining time runs before the redirect (#471).
        if seek_pending is not None and seek_pending():
            return
        if time_expired is not None and time_expired():
            return
        if pause_event is not None and pause_event.is_set():
            # Poll (not a blind block) so a budget expiry that lands DURING the
            # pause wakes us — the top-of-loop time_expired check then returns,
            # letting the caller raise the overrun prompt while still paused.
            _wait_through_pause(pause_event, stop_event, time_expired)
            if stop_event.is_set():
                return
            # Re-check stop/seek/advance/time_expired at the top before consuming
            # more dwell; the resume may have a seek queued behind it.
            continue
        if buffer_provider is not None:
            remaining += buffer_provider()
        slice_dur = min(_SLICE_S, remaining)
        time.sleep(slice_dur)
        remaining -= slice_dur


def make_routes_column():
    # Display name "Electrodes" (the column drives electrode actuation,
    # routes are just one input); col_id stays "routes" — it keys
    # persistence and the ack-wait grid, so renaming it would orphan
    # saved protocols and user-tuned wait times.
    return Column(
        model=RoutesColumnModel(
            col_id="routes", col_name="Routes", default_value=[],
        ),
        view=RoutesSummaryView(),
        handler=RoutesHandler(),
        preference_display_name="Electrodes / Routes"
    )

