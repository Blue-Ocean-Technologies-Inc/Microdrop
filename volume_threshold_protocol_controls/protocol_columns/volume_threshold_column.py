"""Volume-threshold per-step column: model + view + handler + factory.

Single-file layout mirrors peripheral_protocol_controls's magnet_column
and dropbot_protocol_controls's voltage / frequency / droplet columns.

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

from traits.api import Float

from logger.logger_service import get_logger

from dropbot_controller.consts import CAPACITANCE_UPDATED
from device_viewer.consts import CALIBRATION_DATA
from electrode_controller.consts import ELECTRODES_STATE_CHANGE

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)

from ..consts import (
    CAP_POLL_TIMEOUT_S, PHASE_POLL_TIMEOUT_S,
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)

logger = get_logger(__name__)


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


def _capacitance_per_unit_area(liquid, filler):
    """liquid - filler when both are present, non-negative, and
    liquid > filler. Returns None otherwise. Mirrors the legacy
    ForceCalculationService.calculate_capacitance_per_unit_area and the
    logging controller's _capacitance_per_unit_area helper."""
    if liquid is None or filler is None:
        return None
    try:
        liquid = float(liquid)
        filler = float(filler)
    except (TypeError, ValueError):
        return None
    if liquid < 0 or filler < 0 or liquid <= filler:
        return None
    return liquid - filler


class VolumeThresholdColumnModel(BaseColumnModel):
    """Per-step volume threshold (user units, typically µL). 0 disables.

    Stored as a Float trait. The unit is unit-agnostic from the
    column's perspective — the handler multiplies it into the
    target-capacitance formula and the user picks the unit by
    convention with their calibration data.
    """

    def trait_for_row(self):
        return Float(float(self.default_value or 0.0),
                     desc="Volume threshold for this step. Reaches "
                          "target capacitance early-ends the phase. "
                          "0 disables.")


class VolumeThresholdColumnView(DoubleSpinBoxColumnView):
    """Numeric edit; hidden by default like droplet_check / trail knobs.
    User opts the column in via the header right-click menu when they
    want volume-threshold behaviour on a step."""

    renders_on_group = False
    hidden_by_default = True


class VolumeThresholdHandler(BaseColumnHandler):
    """Per-step volume threshold monitor (priority 30 — runs in
    parallel with RoutesHandler).

    Per phase:
      * Read the actuated electrodes from the ELECTRODES_STATE_CHANGE
        payload that RoutesHandler publishes.
      * Drain any pending CALIBRATION_DATA messages and recompute
        capacitance-per-unit-area.
      * target = threshold * actuated_area * cpa
      * Poll CAPACITANCE_UPDATED until current >= target -> set
        ctx.phase_advance_event (RoutesHandler's _cooperative_sleep
        wakes on it) -> loop back for the next phase boundary.
    """

    priority = 30
    wait_for_topics = [
        ELECTRODES_STATE_CHANGE, CAPACITANCE_UPDATED, CALIBRATION_DATA,
    ]

    def on_step(self, row, ctx):
        threshold = float(getattr(row, "volume_threshold", 0.0) or 0.0)
        if threshold <= 0:
            return
        if getattr(ctx.protocol, "preview_mode", False):
            return
        electrode_areas = dict(
            ctx.protocol.scratch.get("electrode_areas") or {}
        )
        if not electrode_areas:
            logger.info(
                "volume_threshold: no electrode_areas in scratch; "
                "skipping (likely a demo / headless run)"
            )
            return

        stop_event = ctx.protocol.stop_event
        cpa = self._latest_cpa(ctx, default=None)

        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
            try:
                payload = ctx.wait_for(
                    ELECTRODES_STATE_CHANGE,
                    timeout=PHASE_POLL_TIMEOUT_S,
                )
            except TimeoutError:
                # Wake up periodically to recheck stop / phases-done.
                continue

            # Phase boundary observed — refresh calibration if a new
            # CALIBRATION_DATA arrived since last time.
            cpa = self._latest_cpa(ctx, default=cpa)
            try:
                electrodes = _json.loads(payload).get("electrodes") or []
            except (TypeError, ValueError):
                continue

            actuated_area = sum(
                float(electrode_areas.get(e, 0.0)) for e in electrodes
            )
            if cpa is None or actuated_area <= 0.0:
                # Cannot compute target — wait for the next phase.
                continue

            target = threshold * actuated_area * cpa
            self._monitor_until_threshold(ctx, target)
            # Do NOT return here — loop back to monitor the NEXT phase.
            # RoutesHandler clears phase_advance_event at the top of its
            # next phase iteration and publishes a fresh
            # ELECTRODES_STATE_CHANGE, which our outer loop picks up.
            # The loop exits only on stop_event or step_phases_done_event
            # (set by RoutesHandler after its final phase).

    @staticmethod
    def _monitor_until_threshold(ctx, target):
        """Poll CAPACITANCE_UPDATED until current_cap >= target (sets
        ctx.phase_advance_event and returns), or stop / step-phases-done
        fires, or the poll times out.

        On TimeoutError we RETURN (not continue) on purpose: returning
        hands control back to on_step's outer loop, which re-waits for
        the next ELECTRODES_STATE_CHANGE and recomputes the target for
        the new phase. CAP_POLL_TIMEOUT_S thus doubles as the cadence at
        which we re-sync to phase boundaries. On real hardware
        capacitance reports arrive sub-second, well inside the poll
        window, so a timeout normally only fires at a genuine lull
        (e.g. between phases)."""
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
                return

    @staticmethod
    def _latest_cpa(ctx, default=None):
        """Drain any pending CALIBRATION_DATA messages and return the
        most recent capacitance-per-unit-area, or `default` if no
        valid calibration arrived. Returns immediately when the
        mailbox is empty (zero timeout)."""
        latest = default
        while True:
            try:
                raw = ctx.wait_for(CALIBRATION_DATA, timeout=0.0)
            except TimeoutError:
                return latest
            try:
                payload = _json.loads(raw)
            except (TypeError, ValueError):
                continue
            value = _capacitance_per_unit_area(
                payload.get("liquid_capacitance_over_area"),
                payload.get("filler_capacitance_over_area"),
            )
            if value is not None:
                latest = value


def make_volume_threshold_column() -> Column:
    return Column(
        model=VolumeThresholdColumnModel(
            col_id=VOLUME_THRESHOLD_COL_ID,
            col_name=VOLUME_THRESHOLD_COL_NAME,
            default_value=VOLUME_THRESHOLD_DEFAULT,
        ),
        view=VolumeThresholdColumnView(
            low=0.0, high=1_000_000.0, decimals=4, single_step=0.01,
        ),
        handler=VolumeThresholdHandler(),
    )
