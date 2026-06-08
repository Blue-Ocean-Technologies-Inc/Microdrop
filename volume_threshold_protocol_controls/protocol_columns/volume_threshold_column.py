"""Volume-threshold per-step column: model + view + handler + factory.

Single-file layout mirrors peripheral_protocol_controls's magnet_column
and dropbot_protocol_controls's voltage / frequency / droplet columns.

The column stores a 0-100 PERCENT (Int). Each phase ends early once the
measured capacitance of the actuated electrodes reaches this percent of
their calibrated FULL (liquid-covered) capacitance:

    target = (percent / 100) * liquid_capacitance_over_area * actuated_area

The filler/baseline value is NOT used in this formula.

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

logger = get_logger(__name__)

# The Redis-backed globals manager, where the device-viewer models publish
# calibration + channel areas on change (device_viewer.models.calibration /
# .electrodes observers). Initialised once at import — the proxy connects
# lazily on first access, so this is import-safe without a running Redis.
# Tests monkeypatch this module attribute with a plain dict.
app_globals = get_microdrop_redis_globals_manager()

_LIQUID_CAP_KEY = "liquid_capacitance_over_area"
_CHANNEL_AREAS_KEY = "channel_electrode_areas_scaled_map"


def _read_full_cap_over_area(app_globals):
    """The FULL (liquid-covered) capacitance-per-unit-area from
    app_globals, or None when absent / non-positive / unparseable."""
    try:
        value = app_globals.get(_LIQUID_CAP_KEY)
    except Exception:                              # pragma: no cover - defensive
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _read_channel_areas(app_globals):
    """channel-id(str) -> summed electrode area (mm^2) from app_globals,
    or {} when absent. Keys are strings because the source Dict(Int,Float)
    is JSON-round-tripped through Redis; callers look up str(channel)."""
    try:
        areas = app_globals.get(_CHANNEL_AREAS_KEY)
    except Exception:                              # pragma: no cover - defensive
        return {}
    return areas if isinstance(areas, dict) else {}


def _parse_capacitance_pf(raw):
    """Pull the numeric pF value out of a CAPACITANCE_UPDATED payload.
    Returns None on any parse failure (handler skips and waits for the
    next reading rather than crashing)."""
    try:
        data = _json.loads(raw)
    except (TypeError, ValueError):
        return None
    cap_str = data.get("capacitance")
    if not isinstance(cap_str, str):
        return None
    try:
        return float(cap_str.split("pF")[0])
    except (ValueError, AttributeError):
        return None


class VolumeThresholdColumnModel(BaseColumnModel):
    """Per-step volume threshold as a PERCENTAGE (0-100; 0 disables).

    Each phase ends early once the measured capacitance of the phase's
    actuated electrodes reaches this percent of their calibrated FULL
    (liquid-covered) capacitance:
        target = (percent / 100) * liquid_capacitance_over_area * actuated_area
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
    ``target = (percent/100) * full_cap_over_area * actuated_area``, and
    poll CAPACITANCE_UPDATED until ``current >= target`` -> set
    ctx.phase_advance_event (RoutesHandler's _cooperative_sleep wakes on
    it) -> loop back for the next phase boundary.

    If the target is NOT reached within the phase's duration, the handler
    opens a recovery dialog via ``ctx.prompt_gui`` (which pauses the run):
    the operator can extend the time + lower the coverage and retry,
    proceed anyway, or stop the run.
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

        full_cap_over_area = _read_full_cap_over_area(app_globals)
        channel_areas = _read_channel_areas(app_globals)
        if full_cap_over_area is None or not channel_areas:
            logger.warning(
                "volume_threshold: missing calibration "
                "(liquid_capacitance_over_area) or channel areas in "
                "app_globals; calibrate + load a device first. Skipping.")
            return

        # The phase's wall-clock budget. RoutesHandler dwells this long per
        # phase (per_phase_dwell = row.duration_s); we treat it as the
        # deadline by which the target must be reached. Missing it opens
        # the recovery dialog.
        phase_duration_s = float(getattr(row, "duration_s", 0.0) or 0.0)

        stop_event = ctx.protocol.stop_event
        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
            try:
                payload = ctx.wait_for(
                    ELECTRODES_STATE_CHANGE, timeout=PHASE_POLL_TIMEOUT_S,
                )
            except TimeoutError:
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
                ctx, row, percent, full_cap_over_area, actuated_area,
                phase_duration_s,
            )
            # Do NOT return — loop back to monitor the next phase.
            # RoutesHandler clears phase_advance_event at the top of its
            # next phase iteration and publishes a fresh
            # ELECTRODES_STATE_CHANGE, which our outer loop picks up. The
            # loop exits only on stop_event or step_phases_done_event.

    def _run_phase(self, ctx, row, percent, full_cap_over_area,
                   actuated_area, phase_duration_s):
        """Monitor one phase to its deadline; on a miss, open the recovery
        dialog and apply the operator's choice (retry / proceed / stop).
        Returns the (possibly updated) coverage percent to carry forward."""
        target = (percent / 100.0) * full_cap_over_area * actuated_area

        # No phase duration => no meaningful "end of phase": fall back to the
        # legacy re-sync cadence (one CAP_POLL_TIMEOUT_S window, no dialog)
        # and let the outer loop re-read the next phase.
        if phase_duration_s <= 0.0:
            self._monitor_until_threshold(
                ctx, target, time.monotonic() + CAP_POLL_TIMEOUT_S)
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
                ctx, target, deadline)
            if status != "timeout":
                # "reached" (phase_advance_event already set) or "stopped".
                return percent

            # Phase duration elapsed without reaching target -> ask the
            # operator. ctx.prompt_gui pauses the run, marshals the dialog
            # onto the GUI thread, and blocks here until they answer (or
            # Stop / external Resume) — no message passing, no actors.
            def _ask():
                d = show_volume_threshold_recovery_dialog(
                    int(percent), last_cap, target,
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

            if action == "stop":
                ctx.protocol.stop_event.set()
                return percent
            if action == "proceed":
                ctx.phase_advance_event.set()
                return percent

            # "retry": apply the new coverage + extension and keep monitoring.
            percent = int(decision.get("new_percent", percent))
            target = (percent / 100.0) * full_cap_over_area * actuated_area
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
        ``last_cap`` is the most recent parsed pF reading (or None)."""
        stop_event = ctx.protocol.stop_event
        last = None
        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
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
