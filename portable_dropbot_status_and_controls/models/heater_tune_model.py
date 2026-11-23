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
step capture's parameters, the running capture's progress, and the last
fit with a proposal per tuning style, which Apply writes after a confirm."""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Dict,
    Enum,
    HasTraits,
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
    HEATER_TUNE_MAX_TEMP_C_BOUNDS,
    HEATER_TUNE_STYLES,
)


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

    start_button = Button("Start Auto-tune")
    cancel_button = Button("Cancel")
    apply_button = Button("Apply...")

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
        """Show a HeaterTuneProgress."""
        self.running = True

        if progress.phase == HEATER_TUNE_FITTING_PHASE:
            self.status = f"ch{progress.channel}: heater off, fitting the model..."
            return

        reading = "-" if progress.current_c is None else f"{progress.current_c:.2f} °C"
        driving = f", driving {progress.duty_pct} %" if progress.duty_pct else ""
        self.status = (
            f"ch{progress.channel} {progress.phase}: {reading}{driving}, "
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
