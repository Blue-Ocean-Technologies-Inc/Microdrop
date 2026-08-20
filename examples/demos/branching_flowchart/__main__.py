"""Entry point.

    python -m examples.demos.branching_flowchart            # the demo
    python -m examples.demos.branching_flowchart --smoke    # headless CI check

Smoke mode builds the full window offscreen, forces every decision to
auto-resolve, runs the seeded protocol end-to-end through the executor,
and exits 0 on protocol_finished — proving the model/executor/canvas
wiring without a display or a human.
"""

import os
import sys


def main():
    smoke = "--smoke" in sys.argv
    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .app import MainWindow

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()

    if not smoke:
        return app.exec()

    # -- smoke: auto-answer every decision, run fast, assert we finish --
    for step in win.protocol.steps:
        step.values["duration_s"] = 0.05
        for node_decisions in [win.scene.node_by_id[step.id].decisions]:
            for handler, spec in node_decisions:
                cfg = step.cfg_for(spec.id)
                cfg.mode = "auto"
                cfg.auto_outcome = spec.default_outcome

    result = {"code": 1}

    def finish(code, label):
        result["code"] = code
        print(f"smoke: protocol {label}")
        app.quit()

    win.executor.signals.protocol_finished.connect(
        lambda: finish(0, "finished"))
    win.executor.signals.protocol_aborted.connect(
        lambda: finish(1, "aborted"))
    win.executor.signals.protocol_error.connect(
        lambda e: finish(1, f"error: {e}"))
    win.executor.signals.log.connect(lambda m: print(f"smoke: {m}"))

    failsafe = QTimer()
    failsafe.setSingleShot(True)
    failsafe.timeout.connect(lambda: finish(2, "TIMED OUT"))
    failsafe.start(60_000)

    win._on_run()
    app.exec()
    return result["code"]


if __name__ == "__main__":
    sys.exit(main())
