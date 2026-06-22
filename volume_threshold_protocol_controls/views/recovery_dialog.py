"""Volume-threshold recovery dialog.

Shown when a step's measured capacitance fails to reach the volume
threshold within the phase's duration. Offers the operator three ways
out:

  * **Apply & retry** — extend the phase by N seconds and/or lower the
    coverage target to Y%, then keep monitoring against the new target.
  * **Proceed anyway** — give up on the threshold for this phase and let
    the protocol continue (the troubleshooting escape hatch).
  * **Pause Protocol** — pause the run (the operator resumes it later from
    the toolbar) instead of aborting.
  * **Rewind** (static steps only) — locate the droplet via a droplet check
    across the route channels and rewind execution to that phase, then
    continue. The dialog only returns the intent; the locating + seek happen
    at the call site (it has no route/phase context).

This module is pure Qt widget code: ``show_volume_threshold_recovery_dialog``
builds a modal dialog, ``exec()``s it, and returns a plain decision dict.
It has no threading or message-passing concerns — the caller marshals it
onto the GUI thread via ``StepContext.prompt_gui`` and reads the returned
dict on the worker thread.

Decision dict shapes:
    {"action": "retry", "extend_s": float, "new_percent": int,
     "count_toward_duration": bool}   # last key only in duration mode
    {"action": "proceed"}
    {"action": "pause"}
    {"action": "rewind"}              # only offered when not duration_mode

``count_toward_duration`` (duration-looping steps only): when True the extra
time is charged against the loop's duration budget (the run still ends on
its configured total); when False (default) the extension is added on top,
so the total run grows by the extension.
"""

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout,
)

# A single extension is capped so a fat-fingered entry can't park the run
# for an hour; the operator can always retry again for another window.
_MAX_EXTEND_S = 600.0
_DEFAULT_EXTEND_S = 5.0


class _RecoveryDialog(QDialog):
    """Two-field recovery prompt with retry / proceed / pause buttons.

    The chosen action is captured in ``self._action``; window-close or Esc
    defaults to "proceed" — the least disruptive outcome (continue the
    run rather than pause it or hang)."""

    def __init__(self, current_percent, current_cap, target_cap,
                 duration_mode=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Volume Threshold Not Reached")
        self.setModal(True)
        self._action = "proceed"          # window-close / Esc default
        self._count_checkbox = None       # only created in duration mode

        current_percent = int(current_percent or 0)

        layout = QVBoxLayout(self)

        cap_line = ""
        if current_cap is not None and target_cap is not None:
            cap_line = (
                f"\nMeasured: {float(current_cap):.2f} pF     "
                f"Target: {float(target_cap):.2f} pF"
            )
        layout.addWidget(QLabel(
            "The volume threshold was not reached within the phase "
            f"duration.\n\nCoverage target: {current_percent}%{cap_line}\n\n"
            "Extend the time and/or lower the coverage target and retry, "
            "or proceed anyway."
        ))

        form = QFormLayout()
        self._extend_spin = QDoubleSpinBox()
        self._extend_spin.setRange(0.0, _MAX_EXTEND_S)
        self._extend_spin.setDecimals(1)
        self._extend_spin.setSingleStep(1.0)
        self._extend_spin.setSuffix(" s")
        self._extend_spin.setValue(_DEFAULT_EXTEND_S)
        form.addRow("Extend time by:", self._extend_spin)

        self._percent_spin = QSpinBox()
        self._percent_spin.setRange(0, 100)
        self._percent_spin.setSuffix(" %")
        self._percent_spin.setValue(current_percent)
        form.addRow("Change coverage to:", self._percent_spin)
        layout.addLayout(form)

        # Duration-looping steps: let the operator decide whether this extra
        # time eats into the loop's duration budget (checked) or extends the
        # total run (unchecked, the default).
        if duration_mode:
            self._count_checkbox = QCheckBox(
                "Count this extra time toward the loop duration\n"
                "(otherwise it extends the total run time)")
            self._count_checkbox.setChecked(False)
            layout.addWidget(self._count_checkbox)

        # "&&" renders a literal ampersand (single "&" is a Qt mnemonic).
        retry_btn = QPushButton("Apply && retry")
        proceed_btn = QPushButton("Proceed anyway")
        pause_btn = QPushButton("Pause Protocol")
        retry_btn.clicked.connect(lambda: self._choose("retry"))
        proceed_btn.clicked.connect(lambda: self._choose("proceed"))
        pause_btn.clicked.connect(lambda: self._choose("pause"))
        retry_btn.setDefault(True)

        buttons = QHBoxLayout()
        buttons.addWidget(retry_btn)
        buttons.addWidget(proceed_btn)
        # Rewind locates the droplet (droplet check across the route channels)
        # and rewinds to that phase, then continues. Only offered for static
        # steps; a duration-mode step's phase loop can't honour a same-step
        # rewind yet, so the button is hidden there.
        if not duration_mode:
            rewind_btn = QPushButton("Rewind")
            rewind_btn.setToolTip(
                "Find the droplet (droplet check across the route) and rewind "
                "to that phase, then continue.")
            rewind_btn.clicked.connect(lambda: self._choose("rewind"))
            buttons.addWidget(rewind_btn)
        buttons.addStretch(1)
        buttons.addWidget(pause_btn)
        layout.addLayout(buttons)

    def _choose(self, action: str) -> None:
        self._action = action
        self.accept()

    def decision(self) -> dict:
        if self._action == "retry":
            d = {
                "action":      "retry",
                "extend_s":    float(self._extend_spin.value()),
                "new_percent": int(self._percent_spin.value()),
            }
            if self._count_checkbox is not None:
                d["count_toward_duration"] = self._count_checkbox.isChecked()
            return d
        return {"action": self._action}


def show_volume_threshold_recovery_dialog(
    current_percent, current_cap=None, target_cap=None, *,
    duration_mode=False, parent=None,
) -> dict:
    """Show the modal recovery dialog and return the operator's decision.

    Must be called on the GUI thread (use ``StepContext.prompt_gui``).

    Args:
        current_percent: the step's current coverage target (0-100).
        current_cap: last measured capacitance in pF (or None — hides the line).
        target_cap: the target capacitance in pF (or None — hides the line).
        duration_mode: when True (the step is looping on a duration budget),
            show the "count toward the loop duration" choice; the returned
            retry dict then carries ``count_toward_duration``.
        parent: dialog parent; None makes it a top-level window so it
            isn't clipped behind the main window during a run.

    Returns one of:
        {"action": "retry", "extend_s": float, "new_percent": int,
         "count_toward_duration": bool}   # last key only when duration_mode
        {"action": "proceed"}
        {"action": "pause"}
    """
    dialog = _RecoveryDialog(current_percent, current_cap, target_cap,
                             duration_mode=duration_mode, parent=parent)
    dialog.exec()
    return dialog.decision()
