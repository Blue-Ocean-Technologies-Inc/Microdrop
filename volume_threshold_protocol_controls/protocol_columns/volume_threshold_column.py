"""Volume-threshold per-step column: model + view + handler + factory.

Single-file layout mirrors peripheral_protocol_controls's magnet_column
and dropbot_protocol_controls's voltage / frequency / droplet columns.

The column stores a 0-100 PERCENT (Int). Each phase ends early once the
measured capacitance of the actuated electrodes reaches this percent of
their calibrated FULL (liquid-covered) capacitance:

threshold_cap = ((percent / 100) * full_electrode_capacitance_over_area + filler_capacitance_over_area) * actuated_area

****** MATH EXPLAINED: WE get this from the following: ****************************************************************

1. Full electrode capacitance over area is liquid_capacitance_over_area - filler_capacitance_over_area from the
device viewer calibrations published on app globals = full_electrode_capacitance_over_area

2. The current capacitance is from the dropbot's capacitance stream. This needs to be normalized by actuated area,
and baseline filler cap subtracted = (current_cap / actuated_area) - filler_capacitance_over_area

3. The user provides the threshold percent from which we can get the
requested_coverage_cap_over_area = (percent / 100) * full_electrode_capacitance_over_area

4. So we need:

(current_cap / actuated_area) - filler_capacitance_over_area >= requested_coverage_cap_over_area

=> current_cap >= (requested_coverage_cap_over_area + filler_capacitance_over_area) * actuated_area

=> threshold_cap = (requested_coverage_cap_over_area + filler_capacitance_over_area) * actuated_area
= ((percent / 100) * full_electrode_capacitance_over_area + filler_capacitance_over_area) * actuated_area

***********************************************************************************************************************

Calibration + area source: read straight from app_globals (the
Redis-backed globals manager). The DV models publish there on change
(device_viewer.models.calibration / .electrodes observers):
  * ``liquid_capacitance_over_area`` (pF/mm^2) — the FULL liquid-covered
    reference.
  * ``channel_electrode_areas_scaled_map`` — channel-id -> summed
    electrode area (mm^2). JSON round-trip through Redis stringifies the
    int keys, so we look up with ``str(channel)``.
This avoids the CALIBRATION_DATA-topic timing trap (that topic fires only
on calibration *change*, pre-run, when no step mailbox exists to receive
it). app_globals always reflects the latest calibrated values.

Re-sync cadence note: the handler recomputes the per-phase target each
time it re-reads ELECTRODES_STATE_CHANGE, which happens whenever
_monitor_until_threshold returns (a CAP_POLL_TIMEOUT_S timeout or a
crossing). On real hardware capacitance reports arrive sub-second, so
re-sync effectively lands at every phase boundary. For protocols with
per-phase dwells shorter than ~CAP_POLL_TIMEOUT_S, several phases can
buffer during one poll and a phase may be evaluated against a slightly
earlier phase's target (correct association, lagging freshness). See the
spec's "Out of scope" section for the rationale and a future fix.
"""

import json as _json
import time

from traits.api import Int

from device_viewer.consts import CHANNEL_AREAS_KEY, FILLER_CAPACITANCE_KEY
from dropbot_protocol_controls.services.force_math import current_full_electrode_capacitance_per_unit_area
from logger.logger_service import get_logger

from microdrop_application.helpers import get_microdrop_redis_globals_manager

from dropbot_controller.consts import CAPACITANCE_UPDATED
from electrode_controller.consts import ELECTRODES_STATE_CHANGE

from pluggable_protocol_tree.builtins.routes_column import (
    PHASE_HOLD_REQUESTED_KEY,
)
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import (
    IntSpinBoxColumnView,
)

from ..consts import (
    CAP_POLL_TIMEOUT_S, PHASE_POLL_TIMEOUT_S,
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)
from ..views.recovery_dialog import show_volume_threshold_recovery_dialog

from microdrop_utils.ureg_helpers import ureg

logger = get_logger(__name__)

# The Redis-backed globals manager, where the device-viewer models publish
# calibration + channel areas on change (device_viewer.models.calibration /
# .electrodes observers). Initialised once at import — the proxy connects
# lazily on first access, so this is import-safe without a running Redis.
# Tests monkeypatch this module attribute with a plain dict.
app_globals = get_microdrop_redis_globals_manager()


def _read_channel_areas():
    """channel-id(str) -> summed electrode area (mm^2) from app_globals,
    or {} when absent. Keys are strings because the source Dict(Int,Float)
    is JSON-round-tripped through Redis; callers look up str(channel)."""
    try:
        areas = app_globals.get(CHANNEL_AREAS_KEY)
    except Exception:                              # pragma: no cover - defensive
        return {}
    return areas if isinstance(areas, dict) else {}


def _parse_capacitance_pf(raw):
    """Pull the capacitance, normalized to pF, out of a CAPACITANCE_UPDATED
    payload. Returns None on any parse failure (handler skips and waits for
    the next reading rather than crashing)."""
    try:
        return ureg(_json.loads(raw).get("capacitance")).to("pF").magnitude
    except Exception as e:
        logger.debug(f"PROTOCOL TREE (volume_threshold_column): Cannot parse capacitance due to error: {e}", exc_info=True)
        return None


def _drain_stale(ctx, topic):
    """Discard every message already queued on ``topic`` so the caller only
    observes readings that arrive afterwards.

    ``CAPACITANCE_UPDATED`` is a continuous stream the DropBot publishes into
    a per-step mailbox that is never cleared between phases. Without this
    drain, a phase would be evaluated against capacitance measured during the
    PREVIOUS phase (before this phase's electrodes were actuated and the
    droplet settled): an end-of-previous-phase HIGH reading would satisfy the
    threshold instantly and advance the phase before any liquid arrived. The
    mailbox is FIFO and returns the oldest item first, so we pop until empty.
    """
    while True:
        try:
            ctx.wait_for(topic, timeout=0.0)
        except TimeoutError:
            return


class VolumeThresholdColumnModel(BaseColumnModel):
    """Per-step volume threshold as a PERCENTAGE (0-100; 0 disables).

    Each phase ends early once the measured capacitance of the phase's
    actuated electrodes reaches this percent of their calibrated FULL
    (liquid-covered) capacitance:
        threshold_cap = ((percent / 100) * full_electrode_capacitance_over_area + filler_capacitance_over_area) * actuated_area
    """

    def trait_for_row(self):
        return Int(int(self.default_value or 0),
                   desc="Volume threshold as a percent (0-100) of the "
                        "actuated electrodes' full (liquid-covered) "
                        "capacitance. Reaching it early-ends the phase. "
                        "0 disables.")


class VolumeThresholdColumnView(IntSpinBoxColumnView):
    """Int percent spinner (0-100); hidden by default like droplet_check
    / trail knobs. User opts the column in via the header right-click
    menu when they want volume-threshold behaviour on a step."""

    renders_on_group = False
    hidden_by_default = True


class VolumeThresholdHandler(BaseColumnHandler):
    """Per-step volume threshold monitor (priority 30 — runs in
    parallel with RoutesHandler).

    Reads the full (liquid-covered) capacitance-per-unit-area and the
    channel-area map from app_globals (published by the DV models).
    Per phase: read the actuated channels from the ELECTRODES_STATE_CHANGE
    payload RoutesHandler publishes, sum their areas, compute
    ``threshold_cap = ((percent/100) * full_cap_over_area + filler_cap_over_area) * actuated_area``,
    and poll CAPACITANCE_UPDATED until ``current >= threshold_cap`` -> set
    ctx.phase_advance_event (RoutesHandler's _cooperative_sleep wakes on
    it) -> loop back for the next phase boundary.

    If the target is NOT reached within the phase's duration, the handler
    opens a recovery dialog via ``ctx.prompt_gui`` (which pauses the run):
    the operator can extend the time + lower the coverage and retry,
    proceed anyway, or pause the run.
    """

    priority = 30
    wait_for_topics = [ELECTRODES_STATE_CHANGE, CAPACITANCE_UPDATED]

    def on_pre_step(self, row, ctx):
        """Hook into RoutesHandler's generic phase-hold mechanism.

        When this step has a threshold set, flag the step so the route driver
        holds each phase open — letting a missed threshold extend the phase
        (buffer) and/or open the recovery dialog instead of advancing on
        schedule. The wiring lives here, in the volume-threshold plugin;
        RoutesHandler only reads the flag (PHASE_HOLD_REQUESTED_KEY) and never
        references volume threshold. on_pre_step runs serially before the
        parallel on_step bucket, so RoutesHandler.on_step sees it.
        """
        try:
            active = float(getattr(row, "volume_threshold", 0) or 0) > 0
        except (TypeError, ValueError):
            active = False
        if active:
            ctx.scratch[PHASE_HOLD_REQUESTED_KEY] = True

    def on_step(self, row, ctx):
        percent = float(getattr(row, "volume_threshold", 0) or 0)
        if percent <= 0:
            return
        if getattr(ctx.protocol, "preview_mode", False):
            return

        # get known quants from globals. the liquid_cap - filler_cap = current_full_electrode_capacitance/area
        # and channel areas to normalize cap readings from dropbot
        full_cap_over_area = current_full_electrode_capacitance_per_unit_area()
        channel_areas = _read_channel_areas()

        if full_cap_over_area is None or not channel_areas:
            logger.warning(
                "volume_threshold: missing calibration "
                "(liquid + filler capacitance) or channel areas in "
                "app_globals; calibrate + load a device first. Skipping.")
            return

        filler_cap_over_area = app_globals.get(FILLER_CAPACITANCE_KEY)

        # The phase's wall-clock budget. RoutesHandler dwells this long per
        # phase (per_phase_dwell = row.duration_s); we treat it as the
        # deadline by which the target must be reached. Missing it opens
        # the recovery dialog.
        phase_duration_s = float(getattr(row, "duration_s", 0.0) or 0.0)

        stop_event = ctx.protocol.stop_event
        pause_event = getattr(ctx.protocol, "pause_event", None)
        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
            # While the run is paused (operator manually moving around the
            # protocol) the column stays inert: it neither picks up actuations
            # nor monitors. On resume, discard anything that arrived during the
            # pause — manual electrode moves and their capacitance — so we only
            # react to the protocol's own next phase, never a manual move.
            if pause_event is not None and pause_event.is_set():
                pause_event.wait_cleared()
                _drain_stale(ctx, ELECTRODES_STATE_CHANGE)
                _drain_stale(ctx, CAPACITANCE_UPDATED)
                continue
            try:
                payload = ctx.wait_for(
                    ELECTRODES_STATE_CHANGE, timeout=PHASE_POLL_TIMEOUT_S,
                )
            except TimeoutError:
                continue
            # A pause that landed while we were blocked in wait_for: ignore
            # this actuation and loop back so the pause branch handles it.
            if pause_event is not None and pause_event.is_set():
                continue
            try:
                channels = _json.loads(payload).get("channels") or []
            except (TypeError, ValueError):
                continue

            actuated_area = sum(
                float(channel_areas.get(str(c), 0.0)) for c in channels
            )
            if actuated_area <= 0.0:
                continue

            # A coverage change the operator makes in the recovery dialog
            # carries forward to subsequent phases of this step.
            percent = self._run_phase(
                ctx, row, percent, full_cap_over_area, filler_cap_over_area, actuated_area,
                phase_duration_s,
            )
            # Do NOT return — loop back to monitor the next phase.
            # RoutesHandler clears phase_advance_event at the top of its
            # next phase iteration and publishes a fresh
            # ELECTRODES_STATE_CHANGE, which our outer loop picks up. The
            # loop exits only on stop_event or step_phases_done_event.

    @staticmethod
    def _threshold_cap(percent, full_cap_over_area, filler_cap_over_area,
                       actuated_area):
        """Target capacitance (pF) the actuated electrodes must reach:
        ``((percent/100) * full_cap_over_area + filler_cap_over_area) * actuated_area``
        (see the module docstring's MATH EXPLAINED block).

        ``full_cap_over_area`` is the full-electrode (liquid-covered) value,
        i.e. ``liquid_capacitance_over_area - filler_capacitance_over_area``.

        With liquid=7.5, filler=1.1 (so full=6.4) pF/mm^2 and a 4.35 mm^2
        electrode, 100% coverage targets the full liquid-covered capacitance
        (== liquid * area == 7.5 * 4.35):

        >>> round(VolumeThresholdHandler._threshold_cap(100, 6.4, 1.1, 4.35), 3)
        32.625

        0% coverage falls back to just the filler baseline (1.1 * 4.35):

        >>> round(VolumeThresholdHandler._threshold_cap(0, 6.4, 1.1, 4.35), 3)
        4.785

        50% coverage sits halfway up the full range above the baseline:

        >>> round(VolumeThresholdHandler._threshold_cap(50, 6.4, 1.1, 4.35), 3)
        18.705

        Zero actuated area -> no target:

        >>> VolumeThresholdHandler._threshold_cap(100, 6.4, 1.1, 0.0)
        0.0

        Zero filler baseline -> pure coverage of the full value (6.4 * 4.35):

        >>> round(VolumeThresholdHandler._threshold_cap(100, 6.4, 0.0, 4.35), 3)
        27.84
        """
        requested_coverage_cap_over_area = (percent / 100) * full_cap_over_area
        return (requested_coverage_cap_over_area
                + filler_cap_over_area) * actuated_area

    def _run_phase(self, ctx, row, percent, full_cap_over_area, filler_cap_over_area,
                   actuated_area, phase_duration_s):
        """
        Monitor one phase to its deadline; on a miss, open the recovery
        dialog and apply the operator's choice (retry / proceed / pause).
        Returns the (possibly updated) coverage percent to carry forward.
        """
        # calculate threshold capacitance
        threshold_cap = self._threshold_cap(
            percent, full_cap_over_area, filler_cap_over_area,
            actuated_area)

        # No phase duration => no meaningful "end of phase": fall back to the
        # legacy re-sync cadence (one CAP_POLL_TIMEOUT_S window, no dialog)
        # and let the outer loop re-read the next phase.
        if phase_duration_s <= 0.0:
            self._monitor_until_threshold(
                ctx, threshold_cap, time.monotonic() + CAP_POLL_TIMEOUT_S)
            return percent

        # When the step is looping on a duration budget, the dialog offers a
        # per-extension choice: charge the extra time to the budget, or add it
        # on top of the total run.
        in_duration_mode = (
            bool(getattr(row, "repeat_duration_controls", False))
            and float(getattr(row, "repeat_duration", 0.0) or 0.0) > 0
        )

        deadline = time.monotonic() + phase_duration_s
        while True:
            status, last_cap = self._monitor_until_threshold(
                ctx, threshold_cap, deadline)
            if status != "timeout":
                # "reached" (phase_advance_event already set) or "stopped".
                return percent

            # Phase duration elapsed without reaching target -> ask the
            # operator. ctx.prompt_gui pauses the run, marshals the dialog
            # onto the GUI thread, and blocks here until they answer (or
            # external Resume) — no message passing, no actors.
            def _ask():
                d = show_volume_threshold_recovery_dialog(
                    int(percent), last_cap, threshold_cap,
                    duration_mode=in_duration_mode)
                if d.get("action") == "retry":
                    extend_s = float(d.get("extend_s", 0.0) or 0.0)
                    # Register the extension while still paused so the route
                    # driver — which is holding this phase open — folds it
                    # into the dwell the instant we resume (no advance race).
                    ctx.add_time_buffer_to_current_phase(extend_s)
                    # In a duration loop, credit the extension back to the
                    # budget (the full duration still runs; total = budget +
                    # extension) UNLESS the operator chose to count it toward
                    # the existing duration (eat into the budget; exact total).
                    if (extend_s > 0 and in_duration_mode
                            and not d.get("count_toward_duration", False)):
                        ctx.note_phase_extension(extend_s)
                return d

            decision = ctx.prompt_gui(_ask) or {"action": "proceed"}
            action = decision.get("action", "proceed")

            if action == "pause":
                # Re-pause after prompt_gui's auto-resume, so the run freezes
                # (RoutesHandler blocks on pause_event while still holding this
                # phase) until the operator resumes from the toolbar.
                ctx.protocol.pause()
                return percent
            if action == "proceed":
                ctx.phase_advance_event.set()
                return percent

            # "retry": apply the new coverage + extension and keep monitoring.
            percent = int(decision.get("new_percent", percent))
            threshold_cap = self._threshold_cap(
                percent, full_cap_over_area, filler_cap_over_area,
                actuated_area)
            extend_s = float(decision.get("extend_s", 0.0) or 0.0)
            deadline = time.monotonic() + max(extend_s, 0.0)

    @staticmethod
    def _monitor_until_threshold(ctx, target, deadline):
        """Poll CAPACITANCE_UPDATED until current_cap >= target (sets
        ctx.phase_advance_event), the ``deadline`` passes, or stop /
        step-phases-done fires.

        Returns ``(status, last_cap)`` where status is:
          * "reached" — target met; phase_advance_event set.
          * "timeout" — deadline elapsed without meeting target.
          * "stopped" — stop_event / step_phases_done_event fired.
        ``last_cap`` is the most recent parsed pF reading (or None).

        While the run is paused this blocks without counting toward the
        deadline or acting on readings, so a pause never advances the phase
        or pops the recovery dialog (which only opens on a genuine timeout)."""
        # Drop capacitance samples buffered before now — they were measured
        # during the previous phase, before this phase's electrodes were
        # actuated, and would otherwise advance the phase prematurely. We only
        # act on readings produced after monitoring begins.
        _drain_stale(ctx, CAPACITANCE_UPDATED)
        stop_event = ctx.protocol.stop_event
        pause_event = getattr(ctx.protocol, "pause_event", None)
        last = None
        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
            # Paused mid-phase: freeze rather than counting down to a timeout
            # (which would pop the dialog) or advancing on a manual reading.
            # Paused time is not charged to the deadline; readings taken while
            # paused are dropped on resume.
            if pause_event is not None and pause_event.is_set():
                paused_at = time.monotonic()
                pause_event.wait_cleared()
                deadline += time.monotonic() - paused_at
                _drain_stale(ctx, CAPACITANCE_UPDATED)
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return "timeout", last
            try:
                cap_payload = ctx.wait_for(
                    CAPACITANCE_UPDATED,
                    timeout=min(CAP_POLL_TIMEOUT_S, remaining),
                )
            except TimeoutError:
                continue
            # A pause that landed while we were blocked in wait_for: drop this
            # reading (don't advance on it) and loop back to the pause branch.
            if pause_event is not None and pause_event.is_set():
                continue
            current = _parse_capacitance_pf(cap_payload)
            if current is None:
                continue
            last = current
            if current >= target:
                ctx.phase_advance_event.set()
                logger.info(
                    "volume_threshold: target reached, phase_advance_event set")
                return "reached", current
        return "stopped", last


def make_volume_threshold_column() -> Column:
    return Column(
        model=VolumeThresholdColumnModel(
            col_id=VOLUME_THRESHOLD_COL_ID,
            col_name=VOLUME_THRESHOLD_COL_NAME,
            default_value=VOLUME_THRESHOLD_DEFAULT,
        ),
        view=VolumeThresholdColumnView(low=0, high=100),
        handler=VolumeThresholdHandler(),
    )
