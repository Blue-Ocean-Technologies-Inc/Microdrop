"""Broker-free wiring for the volume-threshold test app.

Stands in for everything the volume-threshold handler normally needs from
the rest of the system, WITHOUT Redis / Dramatiq / hardware:

  * Seeds calibration + channel areas into the two module-level
    ``app_globals`` the handler reads (the VT column's own, and
    force_math's — ``current_full_electrode_capacitance_per_unit_area``
    reads the latter).
  * Replaces RoutesHandler's electrode-actuation publish with an
    in-process stand-in that feeds ELECTRODES_STATE_CHANGE to the VT
    handler's mailbox and immediately acks ELECTRODES_STATE_APPLIED —
    using ``listener.route_to_active_step``, the documented direct entry
    point into the running step's mailbox.
  * Exposes ``inject(pF)`` to push a CAPACITANCE_UPDATED reading the same
    way, and wraps the handler's ``_drain_stale`` so the app can show how
    many stale readings each phase boundary dropped.

All monkeypatching is reverted by ``teardown()``.
"""

import json

import dropbot_protocol_controls.services.force_math as force_math_mod
import pluggable_protocol_tree.builtins.routes_column as routes_mod
import volume_threshold_protocol_controls.protocol_columns.volume_threshold_column as vt_mod

from device_viewer.consts import (
    CHANNEL_AREAS_KEY, FILLER_CAPACITANCE_KEY, LIQUID_CAPACITANCE_KEY,
)
from dropbot_controller.consts import CAPACITANCE_UPDATED
from electrode_controller.consts import ELECTRODES_STATE_CHANGE
from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.execution.listener import route_to_active_step


# --- the simulated device's calibration ----------------------------------
# liquid - filler = full (liquid-covered) cap/area = 6.4 pF/mm^2.
LIQUID_PF_PER_MM2 = 7.5
FILLER_PF_PER_MM2 = 1.1
ELECTRODE_AREA_MM2 = 4.35
# Three single-electrode phases (channels 0,1,2), each 4.35 mm^2.
CHANNEL_AREAS = {"0": ELECTRODE_AREA_MM2, "1": ELECTRODE_AREA_MM2,
                 "2": ELECTRODE_AREA_MM2}
ELECTRODE_TO_CHANNEL = {"e00": 0, "e01": 1, "e02": 2}


def full_cap_over_area() -> float:
    """The full (liquid-covered) cap/area the handler will compute."""
    return LIQUID_PF_PER_MM2 - FILLER_PF_PER_MM2


def target_pf(percent: float, actuated_area: float = ELECTRODE_AREA_MM2) -> float:
    """The per-phase threshold capacitance for ``percent`` coverage of one
    electrode — same formula as VolumeThresholdHandler._threshold_cap."""
    return ((percent / 100.0) * full_cap_over_area()
            + FILLER_PF_PER_MM2) * actuated_area


class _FakeElectrodePublisher:
    """Stands in for electrode_state_change_publisher: feeds the actuation
    to the VT handler's mailbox and synchronously acks it, so RoutesHandler's
    ``wait_for(ELECTRODES_STATE_APPLIED)`` returns at once (no hardware).

    ``pre_actuate`` (optional) runs FIRST, on this (RoutesHandler's worker)
    thread, before the actuation is delivered. The runner uses it to seed a
    stale-capacitance backlog: anything it injects is guaranteed to be in the
    mailbox before the VT handler wakes on ELECTRODES_STATE_CHANGE and flushes
    — a deterministic happens-before, no thread race.
    """

    def __init__(self, pre_actuate=None):
        self._pre_actuate = pre_actuate

    def publish(self, actuated_channels, *args, **kwargs):
        if self._pre_actuate is not None:
            self._pre_actuate(sorted(actuated_channels))
        payload = json.dumps({"channels": sorted(actuated_channels)})
        route_to_active_step(ELECTRODES_STATE_CHANGE, payload)
        route_to_active_step(ELECTRODES_STATE_APPLIED, "ok")


def inject(pf: float) -> None:
    """Push one CAPACITANCE_UPDATED reading (pF) into the running step's
    mailbox, exactly as the dropbot stream would."""
    route_to_active_step(
        CAPACITANCE_UPDATED, json.dumps({"capacitance": f"{pf} pF"}))


class Harness:
    """Owns the monkeypatches + calibration so the runner can set up once
    and ``teardown()`` cleanly."""

    def __init__(self, on_drained=None, pre_actuate=None):
        # on_drained(count:int): called (on the executor's worker thread)
        # each time a phase boundary drains stale capacitance readings.
        # pre_actuate(channels): runs on the worker thread just before each
        # actuation is delivered — used to seed the stale backlog.
        self._on_drained = on_drained
        self._pre_actuate = pre_actuate
        self._saved = {}
        self.calibration = {
            LIQUID_CAPACITANCE_KEY: LIQUID_PF_PER_MM2,
            FILLER_CAPACITANCE_KEY: FILLER_PF_PER_MM2,
            CHANNEL_AREAS_KEY: dict(CHANNEL_AREAS),
        }

    def setup(self):
        # 1. Seed calibration into both readers (same dict).
        self._saved["force_globals"] = force_math_mod.app_globals
        self._saved["vt_globals"] = vt_mod.app_globals
        force_math_mod.app_globals = self.calibration
        vt_mod.app_globals = self.calibration

        # 2. Stub the hardware-facing publishes in RoutesHandler.
        self._saved["publish_message"] = routes_mod.publish_message
        self._saved["electrode_pub"] = routes_mod.electrode_state_change_publisher
        routes_mod.publish_message = lambda **kwargs: None  # display: no-op
        routes_mod.electrode_state_change_publisher = _FakeElectrodePublisher(
            pre_actuate=self._pre_actuate)

        # 3. Wrap the real _drain_stale so we can report how many stale
        #    readings each phase dropped — while still exercising the fix.
        self._saved["drain"] = vt_mod._drain_stale
        real_drain = vt_mod._drain_stale

        def _instrumented_drain(ctx, topic):
            dropped = _mailbox_size(ctx, topic)
            real_drain(ctx, topic)          # the actual fix under test
            if dropped and self._on_drained is not None:
                self._on_drained(dropped)
        vt_mod._drain_stale = _instrumented_drain

    def teardown(self):
        force_math_mod.app_globals = self._saved.get("force_globals",
                                                      force_math_mod.app_globals)
        vt_mod.app_globals = self._saved.get("vt_globals", vt_mod.app_globals)
        if "publish_message" in self._saved:
            routes_mod.publish_message = self._saved["publish_message"]
        if "electrode_pub" in self._saved:
            routes_mod.electrode_state_change_publisher = self._saved["electrode_pub"]
        if "drain" in self._saved:
            vt_mod._drain_stale = self._saved["drain"]
        self._saved.clear()


def _mailbox_size(ctx, topic) -> int:
    """Best-effort count of queued messages for ``topic`` (for the drained
    readout only). Reaches into the mailbox internals — fine for a harness."""
    try:
        return ctx._mailboxes[topic]._queue.qsize()
    except Exception:                                   # pragma: no cover
        return 0
