# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the heater auto-tune group (More Controls pane): the
step capture's parameters, the running run's progress and live plot, the
last fit with a proposal per tuning style, which Apply writes after a
confirm, and the verify run that checks the gains on the board."""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Dict,
    Enum,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
)

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    HEATER_TUNE_DEFAULT_DURATION_S,
    HEATER_TUNE_DEFAULT_DUTY_PCT,
    HEATER_TUNE_DEFAULT_MAX_TEMP_C,
    HEATER_TUNE_DEFAULT_STYLE,
    HEATER_TUNE_DURATION_S_BOUNDS,
    HEATER_TUNE_DUTY_PCT_BOUNDS,
    HEATER_TUNE_FITTING_PHASE,
    HEATER_TUNE_MARGIN_C,
    HEATER_TUNE_MAX_TEMP_C_BOUNDS,
    HEATER_TUNE_STYLES,
    HEATER_TUNE_VERIFY_DEFAULT_SETPOINT_C,
    HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS,
)

# Local imports.
from ..consts import HEATER_TUNE_VERIFY_SETPOINT_STEP_C
from .heater_tune_plot_model import HeaterTunePlot


class HeaterTuneModel(HasTraits):
    """Heater auto-tune: a duty step on the selected heater, the fitted
    first-order-plus-dead-time model, and proposed PI gains plus the Smith
    predictor model. Mutated only on the GUI thread."""

    # ---- Step capture parameters (the vendor tuning panel's) ----------
    duty_pct = Range(
        *HEATER_TUNE_DUTY_PCT_BOUNDS,
        HEATER_TUNE_DEFAULT_DUTY_PCT,
        mode="spinner",
        desc="manual heater duty of the step (%); a duty whose steady state "
        "stays under the maximum temperature lets the capture see the whole "
        "response",
    )
    max_temp_c = Range(
        *HEATER_TUNE_MAX_TEMP_C_BOUNDS,
        HEATER_TUNE_DEFAULT_MAX_TEMP_C,
        desc="never heated past: heating stops 1.5 °C below it, earlier when "
        "the trend would reach it",
    )
    max_duration_s = Range(
        *HEATER_TUNE_DURATION_S_BOUNDS,
        HEATER_TUNE_DEFAULT_DURATION_S,
        mode="spinner",
        desc="time limit of the heating phase (s)",
    )
    style = Enum(
        HEATER_TUNE_DEFAULT_STYLE,
        HEATER_TUNE_STYLES,
        desc="closed-loop speed of the proposed gains: smooth is the slowest "
        "with the widest margin, fast the quickest",
    )
    persist = Bool(
        False,
        desc="also save the gains and the model to flash; without it they "
        "last until the next reboot",
    )

    # ---- Verify run parameters (cap and time limit: the capture's) ----
    verify_setpoint_c = Range(
        *HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS,
        HEATER_TUNE_VERIFY_DEFAULT_SETPOINT_C,
        desc="set point the board's own loop regulates to; at least 1 °C above "
        "the current reading and 1.5 °C below the maximum temperature",
    )

    start_button = Button("Start Auto-tune")
    cancel_button = Button("Cancel")
    apply_button = Button("Apply...")
    verify_button = Button("Verify")

    # ---- Run state and result -----------------------------------------
    #: A capture (or its fit) runs on the backend: from its first progress
    #: to its done.
    running = Bool(False)
    #: The last progress, refusal or apply outcome.
    status = Str("-")
    #: The heater the last fit belongs to; Apply writes that channel.
    result_channel = Int()
    #: The last fit's plant, one line.
    fit_display = Str("-")
    #: The last fit's proposals by style: {kp, ki, kd, lambda_s, notes}.
    proposals = Dict(Str, Dict)
    #: The last fit's Smith model row: gain °C/%, time constant s, dead s.
    smith_model = List()
    #: The fit's and the model's notes (quality, clamping).
    notes_display = Str()
    #: The last verify run's response figures, one line.
    verify_display = Str("-")
    #: Live temperature and output of the running (or last) run.
    plot = Instance(HeaterTunePlot, ())

    #: The selected style's proposal, one line.
    proposal_display = Property(Str, observe="proposals, style, smith_model")
    #: A finished fit can be written while no capture runs.
    can_apply = Property(Bool, observe="proposals, running")

    def _get_proposal_display(self):
        proposal = self.proposals.get(self.style)

        if proposal is None or not self.smith_model:
            return "-"

        gain, tau_s, dead_s = self.smith_model

        return (
            f"Kp {proposal['kp']:.2f}, Ki {proposal['ki']:.2f}, Kd "
            f"{proposal['kd']:.2f} (λ {proposal['lambda_s']:.0f} s); Smith "
            f"model {gain:g} °C/%, {tau_s:g} s, {dead_s:g} s"
        )

    def _get_can_apply(self):
        return bool(self.proposals) and not self.running

    # ------------------------------------------------------------------ #
    # Backend feedback                                                    #
    # ------------------------------------------------------------------ #

    def adopt_progress(self, progress):
        """Show a HeaterTuneProgress; the first of a run starts its plot."""

        if not self.running:
            self.plot.begin(progress.setpoint_c)

        self.running = True

        if progress.phase == HEATER_TUNE_FITTING_PHASE:
            self.status = f"ch{progress.channel}: heater off, fitting the model..."
            return

        self.plot.add_reading(
            progress.elapsed_s, progress.current_c, float(progress.duty_pct)
        )

        reading = "-" if progress.current_c is None else f"{progress.current_c:.2f} °C"
        driving = f", driving {progress.duty_pct} %" if progress.duty_pct else ""
        target = (
            "" if progress.setpoint_c is None else f" to {progress.setpoint_c:g} °C"
        )
        self.status = (
            f"ch{progress.channel} {progress.phase}{target}: {reading}{driving}, "
            f"{progress.elapsed_s:.0f} s"
        )

    def adopt_done(self, done):
        """Show a HeaterTuneDone: the result, or why there is none (a refusal
        or an aborted capture keeps the previous result)."""
        self.running = False

        if not done.ok:
            self.status = f"ch{done.channel}: no result: {done.reason}"
            return

        fit = done.fit
        self.result_channel = done.channel
        self.smith_model = list(done.smith_model)
        self.proposals = {
            style: proposal.model_dump() for style, proposal in done.proposals.items()
        }
        self.fit_display = (
            f"ch{done.channel}: gain {fit.gain:.3f} °C/%, τ {fit.tau_s:.1f} s, "
            f"dead time {fit.dead_time_s:.2f} s (R² {fit.r2:.3f})"
        )
        self.notes_display = " ".join(done.notes)
        self.status = f"ch{done.channel} done ({done.reason}); heater off"

        self.plot.overlay_fopdt(fit.gain, fit.tau_s, fit.dead_time_s, fit.y0_c)
        self._suggest_verify_setpoint()

    def adopt_verify_done(self, done):
        """Show a HeaterTuneVerifyDone: the response figures (an aborted
        run's too), or why there are none (a refusal keeps the last ones)."""
        self.running = False

        if done.metrics is not None:
            self.verify_display = _verify_summary(done)
            self._suggest_verify_setpoint()

        if done.ok:
            self.status = f"ch{done.channel} verify done ({done.reason}); heater off"
        elif done.metrics is None:
            self.status = f"ch{done.channel}: verify: no result: {done.reason}"
        else:
            self.status = f"ch{done.channel}: verify ended early: {done.reason}"

    def _suggest_verify_setpoint(self):
        """The next verify's set point: the last reading plus
        HEATER_TUNE_VERIFY_SETPOINT_STEP_C, held below the cap minus the run
        margin, where the backend would refuse it."""

        if not self.plot.samples:
            return

        last_c = self.plot.samples[-1][1]
        ceiling_c = self.max_temp_c - HEATER_TUNE_MARGIN_C
        floor_c = HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS[0]
        suggested_c = min(
            max(last_c + HEATER_TUNE_VERIFY_SETPOINT_STEP_C, floor_c), ceiling_c
        )

        self.verify_setpoint_c = round(suggested_c, 1)

    def adopt_applied(self, applied):
        """Show a HeaterTuneApplied, as the vendor panel words it."""

        if applied.error:
            self.status = f"ch{applied.channel}: not applied: {applied.error}"
            return

        if not applied.gains:
            self.status = (
                f"ch{applied.channel}: apply FAILED: gains refused or unanswered "
                f"(nothing changed)"
            )
            return

        parts = ["gains written"]

        if applied.smith == "ok":
            parts.append("Smith model written")
        elif applied.smith == "not served":
            parts.append("Smith model NOT written: this firmware has no temp_smith")
        else:
            parts.append(f"Smith model NOT written ({applied.smith})")

        if applied.gains_persisted is not None:
            parts.append(
                "persisted" if applied.gains_persisted else "gains NOT persisted"
            )

        self.status = f"ch{applied.channel}: {'; '.join(parts)}"


def _verify_summary(done):
    """A HeaterTuneVerifyDone's metrics, one line; figures the record does
    not show are left out."""
    metrics = done.metrics
    parts = []

    if metrics.dead_time_s is not None:
        parts.append(f"dead time {metrics.dead_time_s:.0f} s")

    if metrics.rise_s is not None:
        parts.append(f"rise {metrics.rise_s:.0f} s")

    if metrics.overshoot_pct is not None:
        parts.append(f"overshoot {metrics.overshoot_pct:.1f} %")

    if metrics.settled and metrics.settle_s is not None:
        parts.append(f"settled in {metrics.settle_s:.0f} s (±{done.band_c:g} °C)")
    else:
        parts.append("not settled")

    if metrics.sse_c is not None:
        parts.append(f"steady-state error {metrics.sse_c:+.2f} °C")

    return f"ch{done.channel} to {done.setpoint_c:g} °C: {', '.join(parts)}"
