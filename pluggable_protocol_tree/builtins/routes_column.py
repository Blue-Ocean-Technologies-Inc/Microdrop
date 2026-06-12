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
    duration_loop_parts, iter_phases,
)
from pluggable_protocol_tree.views.columns.base import BaseColumnView


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
                   pause_event, qsignals, phase_index, phase_total,
                   hold_for_buffer=False):
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
        """
        # Fresh slate: a handler set in phase N-1 must NOT carry over into
        # phase N. Cleared before the stop/pause checks so a stale set
        # doesn't accidentally fire here. Same for any unconsumed phase-time
        # buffer left over from a phase that ended early.
        ctx.phase_advance_event.clear()
        ctx.reset_phase_time_buffer()
        if stop_event.is_set():
            return False
        # Pause check at the phase boundary — block here so the
        # next phase's actuation doesn't fire until the user
        # resumes. The executor's between-step pause check
        # doesn't reach inside on_step's phase loop, so without
        # this the routes keep playing through a Pause click.
        if pause_event.is_set():
            pause_event.wait_cleared()
            if stop_event.is_set():
                return False

        electrodes = sorted(phase)
        channels = sorted(mapping[e] for e in electrodes if e in mapping)
        for e in electrodes:
            if e not in mapping:
                logger.warning(
                    f"electrode {e!r} has no channel mapping; "
                    f"actuation channel skipped"
                )

        if qsignals is not None:
            qsignals.phase_started.emit(
                phase_index, phase_total, per_phase_dwell,
            )

        # 1. Display: synchronous, no ack. editable=False so the DV won't
        # echo a hardware publish back at us during a run.
        display_msg = ProtocolTreeDisplayMessage(
            electrodes=electrodes,
            routes=static_routes,
            step_id=step_uuid,
            step_label=step_label,
            free_mode=False,
            editable=False,
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
                           phase_advance_event=ctx.phase_advance_event)

        # Consume any phase-time buffer a sibling column added (only relevant
        # when this step opted into holding — see below) and tell the status
        # bar so its target grows to match. Whether the held time is credited
        # back to a duration budget is the requesting column's policy (it calls
        # ctx.note_phase_extension), not RoutesHandler's — we only hold + report.
        def _take_and_emit():
            extra = ctx.take_phase_time_buffer()
            if extra > 0 and qsignals is not None:
                qsignals.phase_extended.emit(extra)
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
            grace_deadline = time.monotonic() + _HOLD_GRACE_S
            while (not stop_event.is_set()
                   and not ctx.phase_advance_event.is_set()):
                if pause_event.is_set():
                    pause_event.wait_cleared()
                    grace_deadline = time.monotonic() + _HOLD_GRACE_S
                    continue
                extra = _take_and_emit()
                if extra > 0:
                    _cooperative_sleep(
                        extra, stop_event, pause_event,
                        phase_advance_event=ctx.phase_advance_event,
                        buffer_provider=_take_and_emit)
                    grace_deadline = time.monotonic() + _HOLD_GRACE_S
                    continue
                if time.monotonic() >= grace_deadline:
                    break
                time.sleep(_SLICE_S)
        return True

    def _run_dynamic_duration_loop(self, row, *, ctx, mapping, static_routes,
                                   step_uuid, step_label, preview_mode,
                                   per_phase_dwell, stop_event, pause_event,
                                   qsignals, budget):
        """Duration mode + a phase-hold hook: loop the unit cycle as long as
        another FULL-duration cycle still fits the budget, then close with
        the return-to-start phase and idle any sub-cycle remainder.

        A hook column (e.g. volume threshold) cuts each phase short via
        phase_advance_event, so wall-clock elapses slower than
        ``per_phase_dwell`` would predict and more cycles fit -> the freed
        time becomes more loops, not idle. The soft-end ramp-down is
        intentionally absent (duration_loop_parts does not produce it):
        reaching the hook's advance condition guarantees droplet position.
        The phase index is a running counter with total 0 (unknown while
        looping) so the status bar shows the advancing phase number.

        Operator-requested phase extensions (the recovery dialog's "extend by
        X") are CREDITED BACK to the budget: they add to the step's total
        time rather than displacing later cycles. A 1000s budget with a 30s
        stuck-phase extension therefore runs ~1030s total, keeping the full
        1000s of cycling. ``ctx.phase_extension_total()`` accumulates those
        extensions; ``_budget_elapsed`` subtracts them from wall-clock."""
        ramp_up, unit_cycle, return_phase = duration_loop_parts(
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
        cycle_full_time = len(unit_cycle) * per_phase_dwell
        step_start = _monotonic()
        running_idx = 0

        def _budget_elapsed():
            # Wall-clock since step start MINUS operator-requested phase
            # extensions, so those add to the total run time rather than
            # eating into the duration budget.
            return _monotonic() - step_start - ctx.phase_extension_total()

        def _run(phase):
            nonlocal running_idx
            running_idx += 1
            # hold_for_buffer=True: this loop only runs when a column requested
            # the phase-hold hook, so honour the same post-dwell hold/dialog as
            # the static path. A phase whose hook advances early is still cut
            # short by phase_advance_event (so cycles keep fitting the budget);
            # only a held phase can extend / open the dialog.
            return self._run_phase(
                phase, ctx=ctx, mapping=mapping, static_routes=static_routes,
                step_uuid=step_uuid, step_label=step_label,
                preview_mode=preview_mode, per_phase_dwell=per_phase_dwell,
                stop_event=stop_event, pause_event=pause_event,
                qsignals=qsignals, phase_index=running_idx, phase_total=0,
                hold_for_buffer=True)

        for phase in ramp_up:
            if not _run(phase):
                return

        while not stop_event.is_set():
            # Only add a cycle if there's room for a COMPLETE one at full
            # per-phase dwell. cycle_full_time <= 0 (degenerate 0-dwell
            # config) would never gate, so run a single cycle and stop.
            if cycle_full_time <= 0:
                for phase in unit_cycle:
                    if not _run(phase):
                        return
                break
            if _budget_elapsed() + cycle_full_time > budget:
                break
            for phase in unit_cycle:
                if not _run(phase):
                    return

        if return_phase is not None and not stop_event.is_set():
            _run(return_phase)

        remaining = budget - _budget_elapsed()
        if remaining > 0 and not stop_event.is_set():
            _cooperative_sleep(remaining, stop_event, pause_event)

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

        qsignals = getattr(ctx.protocol, "qsignals", None)
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
                qsignals=qsignals,
                budget=float(getattr(row, "repeat_duration", 0.0) or 0.0))
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
            total_phases = len(phases)
            for phase_idx, phase in enumerate(phases, start=1):
                if not self._run_phase(
                        phase, ctx=ctx, mapping=mapping,
                        static_routes=routes, step_uuid=step_uuid,
                        step_label=step_label, preview_mode=preview_mode,
                        per_phase_dwell=per_phase_dwell, stop_event=stop_event,
                        pause_event=pause_event, qsignals=qsignals,
                        phase_index=phase_idx, phase_total=total_phases,
                        hold_for_buffer=phase_hold):
                    break
            # Route Reps Dur mode: after the full cycles, hold the last
            # phase's electrodes (no new publish) for the exact leftover so
            # total step time lands on the budget precisely. Based on the
            # ACTUAL emitted phase count so it accounts for loop cycles,
            # ramps, and routes.
            if in_duration_mode and not stop_event.is_set():
                pad = max(0.0, float(getattr(row, "repeat_duration", 0.0))
                              - len(phases) * per_phase_dwell)
                if pad > 0:
                    _cooperative_sleep(pad, stop_event, pause_event)

        # Tell DurationColumnHandler we already covered the dwell.
        ctx.scratch[DURATION_CONSUMED_KEY] = True
        # Signal sibling parallel-bucket handlers (e.g. VolumeThresholdHandler)
        # that the per-phase loop is done so they can exit their wait loops
        # cleanly. Without this, handlers blocked in
        # wait_for(ELECTRODES_STATE_CHANGE) for a next phase that will never
        # come would block the bucket's ThreadPoolExecutor indefinitely.
        ctx.step_phases_done_event.set()


def _cooperative_sleep(seconds: float, stop_event, pause_event=None,
                       phase_advance_event=None, buffer_provider=None) -> None:
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
    """
    remaining = seconds
    while remaining > 0:
        if stop_event.is_set():
            return
        if phase_advance_event is not None and phase_advance_event.is_set():
            return
        if pause_event is not None and pause_event.is_set():
            pause_event.wait_cleared()
            if stop_event.is_set():
                return
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
            col_id="routes", col_name="Electrodes", default_value=[],
        ),
        view=RoutesSummaryView(),
        handler=RoutesHandler(),
    )

