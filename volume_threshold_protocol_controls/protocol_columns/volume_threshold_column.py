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

from traits.api import Int

from logger.logger_service import get_logger

from microdrop_application.helpers import get_microdrop_redis_globals_manager

from dropbot_controller.consts import CAPACITANCE_UPDATED
from electrode_controller.consts import ELECTRODES_STATE_CHANGE

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
    """

    priority = 30
    wait_for_topics = [ELECTRODES_STATE_CHANGE, CAPACITANCE_UPDATED]

    def on_step(self, row, ctx):
        percent = float(getattr(row, "volume_threshold", 0) or 0)
        if percent <= 0:
            return
        if getattr(ctx.protocol, "preview_mode", False):
            return

        full_cap_over_area = _read_full_cap_over_area(app_globals)
        channel_areas = _read_channel_areas(app_globals)
        if full_cap_over_area is None or not channel_areas:
            logger.info(
                "volume_threshold: missing calibration "
                "(liquid_capacitance_over_area) or channel areas in "
                "app_globals; calibrate + load a device first. Skipping.")
            return

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

            target = (percent / 100.0) * full_cap_over_area * actuated_area
            self._monitor_until_threshold(ctx, target)
            # Do NOT return — loop back to monitor the next phase.
            # RoutesHandler clears phase_advance_event at the top of its
            # next phase iteration and publishes a fresh
            # ELECTRODES_STATE_CHANGE, which our outer loop picks up. The
            # loop exits only on stop_event or step_phases_done_event.

    @staticmethod
    def _monitor_until_threshold(ctx, target):
        """Poll CAPACITANCE_UPDATED until current_cap >= target (sets
        ctx.phase_advance_event and returns), or stop / step-phases-done
        fires, or the poll times out.

        On TimeoutError we RETURN (not continue) on purpose: returning
        hands control back to on_step's outer loop, which re-waits for
        the next ELECTRODES_STATE_CHANGE and recomputes the target for
        the new phase. CAP_POLL_TIMEOUT_S thus doubles as the cadence at
        which we re-sync to phase boundaries."""
        stop_event = ctx.protocol.stop_event
        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
            try:
                cap_payload = ctx.wait_for(
                    CAPACITANCE_UPDATED, timeout=CAP_POLL_TIMEOUT_S,
                )
            except TimeoutError:
                return
            current = _parse_capacitance_pf(cap_payload)
            if current is None:
                continue
            if current >= target:
                ctx.phase_advance_event.set()
                logger.info(
                    "volume_threshold: target reached, phase_advance_event set")
                return


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
