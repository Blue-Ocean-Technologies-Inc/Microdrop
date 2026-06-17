"""Broker-free Qt app that proves the volume-threshold stale-capacitance fix.

Runs a REAL ProtocolExecutor over a single 3-phase volume-threshold step,
with no Redis / Dramatiq / hardware (see vt_test_harness). A scripted
capacitance timeline drives each phase:

  * At the phase boundary the fake hardware seeds a STALE high-capacitance
    backlog (readings "left over" from the previous phase) into the mailbox
    *before* the VT handler starts monitoring.
  * The handler must FLUSH those stale readings (the fix) and then HOLD —
    not advance — until a genuine crossing arrives.
  * A fresh "below target" stream holds the phase; at +1.5 s a genuine
    crossing reading arrives and the phase advances.

If the fix works, every phase holds ~1.5 s and advances on the crossing.
Without it, a phase would advance almost immediately on the stale backlog.
The verdict (phase hold durations) drives a PASS/FAIL banner.

Run::

    pixi run python -m volume_threshold_protocol_controls.demos.run_volume_threshold_test
    ... --selftest      # headless (QT_QPA_PLATFORM=offscreen); exit 0 = PASS
    ... --no-flush      # simulate the pre-fix bug (stale readings advance)
    ... --pause-test    # pause mid-phase; verify the column stays inert
"""

import sys
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager
from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
    make_volume_threshold_column,
)

from . import vt_test_harness as H
from .vt_test_panel import VTTestPanel


# --- scenario knobs -------------------------------------------------------
VT_PERCENT = 80              # coverage threshold for the step
DWELL_S = 3.0                # per-phase dwell (the miss deadline)
CROSS_DELAY_S = 1.5          # when the genuine crossing arrives in a phase
LOW_PF = 12.0                # fresh "below target" reading
CROSS_PF = 33.0              # fresh "crossing" reading (>= target)
STALE_PF = 99.0              # stale leftover reading seeded at each boundary
STALE_BURST = 4              # how many stale readings to seed per boundary
INJECT_INTERVAL_MS = 50      # capacitance stream cadence

# Verdict window: a phase should HOLD well past the stale spike (>= MIN_HOLD)
# and advance on the crossing BEFORE the dwell/dialog (< MAX_HOLD).
MIN_HOLD_S = 1.0
MAX_HOLD_S = 2.9

# --pause-test scenario: pause mid-phase, simulate the operator "manually
# moving around" by streaming an above-target reading, hold paused PAST the
# dwell (so a non-pause-aware column would time out and pop the dialog), then
# resume and cross. A pause-aware column must advance only after resume.
PAUSE_AT_S = 0.3
RESUME_AT_S = 4.0          # > DWELL_S, so a non-pause-aware run would time out
PAUSE_CROSS_S = 4.3
MANUAL_HIGH_PF = 99.0      # "manual move" reading injected during the pause


class _Sim:
    """Shared current simulated capacitance (pF). Attribute read/write is
    atomic under the GIL, so the worker thread (pre_actuate) and the GUI
    thread (injector) can touch it without a lock."""
    def __init__(self, value):
        self.value = float(value)


class _Bridge(QObject):
    """Marshals worker-thread harness callbacks onto the GUI thread."""
    drained = Signal(int)            # stale readings flushed at a phase start
    seeded = Signal(int)             # stale readings seeded before a phase
    reached = Signal(float)          # monotonic time VT's monitor hit the target


def _build_protocol() -> RowManager:
    rm = RowManager(columns=[
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(), make_electrodes_column(),
        make_routes_column(), make_trail_length_column(),
        make_volume_threshold_column(),
    ])
    rm.protocol_metadata["electrode_to_channel"] = dict(H.ELECTRODE_TO_CHANNEL)
    rm.add_step(values={
        "name": "VT stale-cap test",
        "duration_s": DWELL_S,
        "routes": [["e00", "e01", "e02"]],   # 3 single-electrode phases
        "trail_length": 1,
        "volume_threshold": VT_PERCENT,
    })
    return rm


def main() -> int:
    # --selftest: run the same flow headless (use QT_QPA_PLATFORM=offscreen),
    # auto-quit on the verdict, and exit 0 (PASS) / 1 (FAIL). Lets the demo
    # double as a smoke check without anyone watching the window.
    selftest = "--selftest" in sys.argv
    # --pause-test: pause mid-phase and verify the column stays inert (no
    # advance on the manual reading, no recovery dialog) until resumed.
    pause_test = "--pause-test" in sys.argv

    app = QApplication(sys.argv)
    panel = VTTestPanel()
    sim = _Sim(LOW_PF)
    bridge = _Bridge()
    target = H.target_pf(VT_PERCENT)
    result = {"ok": None}
    _t0 = time.monotonic()

    def L(msg):
        panel.log(f"[{time.monotonic() - _t0:6.2f}s] {msg}")

    # --- harness callbacks (run on the executor's worker thread) ----------
    def pre_actuate(channels):
        """Seed the stale backlog for the phase that's about to start, then
        drop the stream to 'below target'. Runs before the actuation reaches
        the VT handler, so these readings are guaranteed stale."""
        for _ in range(STALE_BURST):
            H.inject(STALE_PF)
        sim.value = LOW_PF
        bridge.seeded.emit(STALE_BURST)

    def on_drained(count):
        bridge.drained.emit(count)

    harness = H.Harness(on_drained=on_drained, pre_actuate=pre_actuate)
    harness.setup()

    # Hook the handler's monitor so we learn the EXACT moment a phase reaches
    # its target (sets phase_advance). This is the true "advance" time — more
    # accurate than step_finished, which on the terminal phase lags ~2s while
    # the handler's outer loop does a final wait_for(ELECTRODES_STATE_CHANGE).
    import volume_threshold_protocol_controls.protocol_columns.volume_threshold_column as _vtmod
    _orig_monitor = _vtmod.VolumeThresholdHandler._monitor_until_threshold

    def _monitor_logged(ctx, target_cap, deadline):
        status, last = _orig_monitor(ctx, target_cap, deadline)
        if status == "reached":
            bridge.reached.emit(time.monotonic())
        return status, last
    _vtmod.VolumeThresholdHandler._monitor_until_threshold = staticmethod(
        _monitor_logged)

    # --no-flush: simulate the PRE-FIX behavior (don't drop stale readings) to
    # show the bug reproduce — phases then advance on the buffered spike.
    if "--no-flush" in sys.argv:
        _vtmod._drain_stale = lambda ctx, topic: None
        L("--no-flush: stale-capacitance flush DISABLED (expect FAIL)")

    # Spy on the recovery dialog: it must NEVER open during a pause. The spy
    # records the fact and returns "proceed" so a headless run can't block on a
    # real modal dialog.
    dialog_fired = {"v": False}
    _orig_dialog = _vtmod.show_volume_threshold_recovery_dialog

    def _dialog_spy(*args, **kwargs):
        dialog_fired["v"] = True
        L("   !!! recovery dialog opened (unexpected during a pause)")
        return {"action": "proceed"}
    _vtmod.show_volume_threshold_recovery_dialog = _dialog_spy

    # --- per-phase timing + verdict state ---------------------------------
    # phase_starts[i] / reach_times[i] pair by index: phase i+1's start and
    # the time its monitor crossed the target. Latency = reach - start.
    phase_starts: list = []
    reach_times: list = []
    resume_times: list = []          # pause-test: when each phase was resumed
    total_phases = {"n": 0}

    def _schedule_cross(delay_s):
        def _cross():
            sim.value = CROSS_PF
            L(f"   injected genuine crossing {CROSS_PF:.0f} pF "
              f"(>= target {target:.1f})")
        QTimer.singleShot(int(delay_s * 1000), _cross)

    def on_phase_started(idx, total, dwell):
        phase_starts.append(time.monotonic())
        total_phases["n"] = total
        panel.set_phase(idx, total, target)
        L(f"phase {idx}/{total} started (dwell {dwell:.1f}s, "
          f"target {target:.2f} pF)")

        if not pause_test:
            _schedule_cross(CROSS_DELAY_S)
            return

        # Pause scenario: pause mid-phase, "manually" stream an above-target
        # reading, hold paused past the dwell, then resume and cross.
        def _pause():
            sim.value = MANUAL_HIGH_PF
            ex.pause()
            L(f"   PAUSED — operator 'manually' streaming {MANUAL_HIGH_PF:.0f} "
              f"pF (>= target; must NOT advance or open the dialog)")

        def _resume():
            ex.resume()
            sim.value = LOW_PF
            resume_times.append(time.monotonic())
            L("   RESUMED — back to a below-target stream")

        QTimer.singleShot(int(PAUSE_AT_S * 1000), _pause)
        QTimer.singleShot(int(RESUME_AT_S * 1000), _resume)
        _schedule_cross(PAUSE_CROSS_S)

    def on_reached(t):
        idx = len(reach_times)               # 0-based phase this belongs to
        reach_times.append(t)
        latency = t - phase_starts[idx] if idx < len(phase_starts) else float("nan")
        L(f"   -> phase {idx + 1} reached target after {latency:.2f}s")

    def _finish(text_prefix=""):
        injector.stop()
        expected = total_phases["n"] or len(phase_starts)
        missed = expected - len(reach_times)
        detail_nums: list = []

        if pause_test:
            # Pass requires: every phase reached the target only AFTER it was
            # resumed (so it ignored the manual reading during the pause), and
            # the recovery dialog never opened.
            n = min(len(reach_times), len(resume_times))
            during_pause = [i + 1 for i in range(n)
                            if reach_times[i] < resume_times[i] - 0.1]
            ok = (expected > 0 and missed == 0
                  and not during_pause and not dialog_fired["v"])
            if ok:
                text = (f"all {expected} phases stayed inert while paused — no "
                        f"advance on the manual reading, no recovery dialog")
            elif dialog_fired["v"]:
                text = "the recovery dialog opened during a pause"
            elif during_pause:
                text = f"phase(s) {during_pause} advanced WHILE paused"
            else:
                text = f"{missed} phase(s) never reached the target"
            detail_nums = [round(reach_times[i] - resume_times[i], 2)
                           for i in range(n)]
            metric = "reach-after-resume(s)"
        else:
            n = min(len(reach_times), len(phase_starts))
            latencies = [reach_times[i] - phase_starts[i] for i in range(n)]
            fast = [i + 1 for i, d in enumerate(latencies) if d < MIN_HOLD_S]
            slow = [i + 1 for i, d in enumerate(latencies) if d > MAX_HOLD_S]
            ok = expected > 0 and missed == 0 and not fast and not slow
            if ok:
                text = (f"all {expected} phases ignored the stale spike and "
                        f"advanced on the real crossing")
            elif fast:
                d = ", ".join(f"{latencies[i - 1]:.2f}s" for i in fast)
                text = f"phase(s) {fast} advanced on a STALE reading ({d})"
            elif missed:
                text = f"{missed} phase(s) never reached the target (timed out)"
            else:
                text = f"phase(s) {slow} advanced suspiciously late"
            detail_nums = [round(d, 2) for d in latencies]
            metric = "latencies(s)"

        panel.set_verdict(ok, text_prefix + text)
        L(f"VERDICT: {'PASS' if ok else 'FAIL'} — {metric}={detail_nums}")
        harness.teardown()
        result["ok"] = ok
        if selftest:
            print("---- event log ----")
            print(panel.log_text())
            print("-------------------")
            print(f"SELFTEST {'PASS' if ok else 'FAIL'}: {text} "
                  f"({metric}={detail_nums})")
            QTimer.singleShot(50, app.quit)

    def on_protocol_error(msg):
        injector.stop()
        L(f"ERROR: {msg}")
        panel.set_verdict(False, f"executor error: {msg}")
        harness.teardown()

    # --- capacitance stream (GUI thread) ----------------------------------
    injector = QTimer()
    injector.setInterval(INJECT_INTERVAL_MS)

    last_injected = {"pf": None}

    def _tick():
        pf = sim.value
        H.inject(pf)
        panel.set_reading(pf, holding=(pf < target))
        if pf != last_injected["pf"]:
            L(f"   stream -> {pf:.0f} pF")
            last_injected["pf"] = pf
    injector.timeout.connect(_tick)

    # --- wire signals -----------------------------------------------------
    ex = ProtocolExecutor(row_manager=_build_protocol())
    ex.signals.phase_started.connect(on_phase_started)
    ex.signals.protocol_finished.connect(lambda: _finish())
    ex.signals.protocol_aborted.connect(lambda: _finish("aborted — "))
    ex.signals.protocol_error.connect(on_protocol_error)
    bridge.reached.connect(on_reached)
    bridge.seeded.connect(
        lambda n: L(f"   (seeded {n} stale {STALE_PF:.0f} pF readings "
                    f"before phase)"))
    bridge.drained.connect(
        lambda n: L(f"   FLUSHED {n} stale reading(s) at phase start"))

    panel.log(f"target for {VT_PERCENT}% coverage of one "
              f"{H.ELECTRODE_AREA_MM2} mm^2 electrode = {target:.2f} pF")
    panel.log(f"(liquid {H.LIQUID_PF_PER_MM2}  filler {H.FILLER_PF_PER_MM2} "
              f"-> full {H.full_cap_over_area():.1f} pF/mm^2)\n")
    panel.show()

    if selftest:
        # Watchdog so a hang can't block CI forever.
        QTimer.singleShot(30_000, app.quit)

    injector.start()
    QTimer.singleShot(300, lambda: ex.start(preview_mode=False))
    app.exec()
    if selftest:
        return 0 if result["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
