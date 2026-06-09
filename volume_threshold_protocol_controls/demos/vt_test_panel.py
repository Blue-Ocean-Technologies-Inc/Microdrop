"""Lightweight Qt view for the volume-threshold test app.

Pure display: the runner pushes state in via these slots (all called on the
GUI thread). Shows the current phase, this phase's target vs the latest
injected capacitance, a HOLD/ADVANCE status, a running event log, and a
big PASS/FAIL banner once the run finishes.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)


class VTTestPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Volume Threshold — stale-capacitance test")
        self.resize(560, 460)

        layout = QVBoxLayout(self)

        title = QLabel("Volume Threshold stale-capacitance test")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self._phase = QLabel("Phase –/–   target – pF")
        self._phase.setStyleSheet("font-family: monospace; font-size: 13px;")
        layout.addWidget(self._phase)

        self._reading = QLabel("current – pF    status: –")
        self._reading.setStyleSheet("font-family: monospace; font-size: 13px;")
        layout.addWidget(self._reading)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self._log, stretch=1)

        self._banner = QLabel("running…")
        self._banner.setAlignment(Qt.AlignCenter)
        self._banner.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 10px; "
            "background: #444; color: white; border-radius: 4px;")
        layout.addWidget(self._banner)

        self._target = 0.0

    # --- slots (GUI thread) ---------------------------------------------

    def set_phase(self, idx: int, total: int, target_pf: float) -> None:
        self._target = target_pf
        self._phase.setText(
            f"Phase {idx}/{total}   target {target_pf:.2f} pF")

    def set_reading(self, pf: float, holding: bool) -> None:
        status = "HOLD" if holding else "ADVANCE"
        rel = "below" if pf < self._target else "≥ target"
        self._reading.setText(
            f"current {pf:6.2f} pF  ({rel})    status: {status}")

    def log(self, message: str) -> None:
        self._log.appendPlainText(message)

    def log_text(self) -> str:
        return self._log.toPlainText()

    def set_verdict(self, passed: bool, text: str) -> None:
        color = "#1a7f37" if passed else "#b3261e"
        label = "PASS" if passed else "FAIL"
        self._banner.setText(f"STALE-CAP FIX: {label} — {text}")
        self._banner.setStyleSheet(
            f"font-size: 16px; font-weight: bold; padding: 10px; "
            f"background: {color}; color: white; border-radius: 4px;")
