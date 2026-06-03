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
    ELECTRODES_STATE_APPLIED,
    PROTOCOL_TREE_DISPLAY_STATE,
)
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)
from pluggable_protocol_tree.services.phase_math import iter_phases
from pluggable_protocol_tree.views.columns.base import BaseColumnView


logger = logging.getLogger(__name__)

# Sentinel set on ctx.scratch by RoutesHandler so DurationColumnHandler
# (priority 90) knows the per-phase dwells have already covered the
# row's total duration and shouldn't be slept again.
DURATION_CONSUMED_KEY = "_routes_consumed_duration"

# Cooperative-sleep slice: how often to check stop_event during a
# per-phase dwell so a Stop press lands within ~50ms even on long
# durations.
_SLICE_S = 0.05

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

    def _run_phase(self, phase, *, ctx, mapping, static_routes, step_uuid,
                   step_label, preview_mode, per_phase_dwell, stop_event,
                   pause_event, qsignals, phase_index, phase_total):
        """Run ONE phase: clear the early-advance event, honour stop/pause,
        publish display (+ hardware when not preview), wait the ack, and
        dwell (cut short by phase_advance_event). Returns False if a Stop
        landed before/at this phase (caller should break its loop), True
        otherwise.

        ``phase_total`` is 0 for the dynamic loop (total unknown while
        looping); callers in the static path pass the materialized count.
        """
        # Fresh slate: a handler set in phase N-1 must NOT carry over into
        # phase N. Cleared before the stop/pause checks so a stale set
        # doesn't accidentally fire here.
        ctx.phase_advance_event.clear()
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

        # 2. Hardware: only when not preview. Gating happens on the sender
        # side by simply not publishing.
        if not preview_mode:
            payload = {"electrodes": electrodes, "channels": channels}
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps(payload),
            )
            # 5.0s timeout matches ack_roundtrip_column. Cold-
            # broker first publish pays ~1-2s; typical ack <100ms.
            # In preview we skip this entirely so the user gets a
            # snappy visual playback with no per-phase 5s stalls.
            ctx.wait_for(ELECTRODES_STATE_APPLIED, timeout=5.0)

        _cooperative_sleep(per_phase_dwell, stop_event, pause_event,
                           phase_advance_event=ctx.phase_advance_event)
        return True

    def on_step(self, row, ctx):
        mapping = ctx.protocol.scratch.get("electrode_to_channel", {})
        per_phase_dwell = float(getattr(row, "duration_s", 0.0) or 0.0)
        stop_event = ctx.protocol.stop_event
        pause_event = ctx.protocol.pause_event
        preview_mode = bool(getattr(ctx.protocol, "preview_mode", False))

        # Cached per-step display message metadata. Routes stay
        # constant across phases — only the active-electrode set
        # changes per phase. step_label format matches the dotted-path
        # convention used elsewhere ("Step 1.2").
        step_uuid = getattr(row, "uuid", "") or ""
        dotted_id = ".".join(str(i + 1) for i in row.path)
        step_label = f"Step {dotted_id}"

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

        # Materialize so we know the total upfront for phase_started's
        # (i, N) emission. Phase counts are bounded by step config and
        # well within reasonable list sizes; no streaming benefit lost.
        phases = list(iter_phases(
            static_electrodes=list(getattr(row, "electrodes", []) or []),
            routes=routes,
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
        qsignals = getattr(ctx.protocol, "qsignals", None)
        for phase_idx, phase in enumerate(phases, start=1):
            if not self._run_phase(
                    phase, ctx=ctx, mapping=mapping,
                    static_routes=static_routes, step_uuid=step_uuid,
                    step_label=step_label, preview_mode=preview_mode,
                    per_phase_dwell=per_phase_dwell, stop_event=stop_event,
                    pause_event=pause_event, qsignals=qsignals,
                    phase_index=phase_idx, phase_total=total_phases):
                break
        # Route Reps Dur mode: after the full cycles, hold the last phase's
        # electrodes (no new publish) for the exact leftover so total step
        # time lands on the budget precisely. Based on the ACTUAL emitted
        # phase count so it accounts for loop cycles, ramps, and routes.
        if in_duration_mode and not stop_event.is_set():
            pad = max(0.0, float(getattr(row, "repeat_duration", 0.0))
                          - len(phases) * per_phase_dwell)
            if pad > 0:
                _cooperative_sleep(pad, stop_event, pause_event)
        # Tell DurationColumnHandler we already covered the dwell.
        ctx.scratch[DURATION_CONSUMED_KEY] = True
        # Signal sibling parallel-bucket handlers (e.g.
        # VolumeThresholdHandler) that the per-phase loop is done so
        # they can exit their wait loops cleanly. Without this,
        # handlers blocked in wait_for(ELECTRODES_STATE_CHANGE) for a
        # next phase that will never come would block the bucket's
        # ThreadPoolExecutor indefinitely.
        ctx.step_phases_done_event.set()


def _cooperative_sleep(seconds: float, stop_event, pause_event=None,
                       phase_advance_event=None) -> None:
    """Sleep for ``seconds``, waking every _SLICE_S to check stop_event
    (and pause_event if provided). Used so a Stop or Pause press lands
    within ~50ms even mid-dwell. On pause: block in
    ``pause_event.wait_cleared()`` until the user resumes, then
    continue with the remaining dwell. Returns early on stop, on
    phase_advance_event (any handler can set it to cut the phase short),
    or when seconds reaches 0."""
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
        slice_dur = min(_SLICE_S, remaining)
        time.sleep(slice_dur)
        remaining -= slice_dur


def make_routes_column():
    return Column(
        model=RoutesColumnModel(
            col_id="routes", col_name="Routes", default_value=[],
        ),
        view=RoutesSummaryView(),
        handler=RoutesHandler(),
    )

