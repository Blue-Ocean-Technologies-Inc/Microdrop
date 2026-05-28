# End-of-Protocol Dialogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the legacy `protocol_grid` end-of-run UX (auto-save protocol, "Create New Experiment?" / "Generate Run Summary?" confirms, report-saved success dialog, preview-complete info) into the pluggable protocol tree, working with the controller's deferred settling flush.

**Architecture:** `ProtocolLoggingController` gains an optional report flag, a completion callback fired after the (deferred) flush, and a `log_metadata` forwarder — staying Qt-free. `ProtocolTreePane` threads a run outcome (`finished`/`aborted`/`error`) into its single terminal point, runs a dialog flow that branches per outcome, auto-saves the protocol, and shows the report-link success dialog when the callback fires. Error is treated like a force-stop (prompts for a summary, after the error dialog).

**Tech Stack:** Python, Traits/PySide6 (pyface.qt), `microdrop_application.dialogs.pyface_wrapper` (`confirm`/`success`/`information`, `YES`/`NO`), pytest.

**Spec:** `docs/superpowers/specs/2026-05-25-ppt-end-of-protocol-dialogs-design.md`

**Conventions for this codebase:**
- All dialogs go through `microdrop_application.dialogs.pyface_wrapper` — never raw `QMessageBox`.
- Use f-strings for all string building (including logs).
- Logging: `from logger.logger_service import get_logger; logger = get_logger(__name__)` (already imported in both files).
- Run tests from the `src/` directory so imports resolve. The repo conftest skips the whole `pluggable_protocol_tree/tests` session when Redis is down **unless test files are named explicitly**, so always name the file.

---

## File Structure

- `pluggable_protocol_tree/services/logging/controller.py` — **Modify.** Add `completion_callback` ctor kwarg, `log_metadata` forwarder, `generate_report` flag on `stop_logging`, conditional report + callback in `_flush`.
- `pluggable_protocol_tree/tests/test_logging_controller.py` — **Modify.** Add tests for the report flag, callback, and metadata forwarder.
- `pluggable_protocol_tree/views/protocol_tree_pane.py` — **Modify.** Import `success`/`information`/`YES`/`QUrl`; construct the controller with the completion callback; add `_on_logging_complete`, `_run_completion_flow`; thread `outcome` through `_on_protocol_terminated` and its three callers; reorder `_on_error`.
- `pluggable_protocol_tree/tests/test_protocol_tree_pane.py` — **Modify.** Add tests for the completion flow (finished / aborted / preview / no-experiment-manager), the success callback, and the error ordering.

---

## Task 1: Controller — optional report, completion callback, metadata forwarder

**Files:**
- Modify: `pluggable_protocol_tree/services/logging/controller.py:51-119`
- Test: `pluggable_protocol_tree/tests/test_logging_controller.py`

- [ ] **Step 1: Write the failing tests**

Append to `pluggable_protocol_tree/tests/test_logging_controller.py` (it already defines `_FakeRow`, `_ctx`, `_immediate` at the top — reuse them):

```python
def test_stop_logging_generate_report_false_writes_data_no_report(tmp_path):
    captured = []
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate,
                                  completion_callback=captured.append)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    c.stop_logging(completed_steps=1, generate_report=False)
    assert list((tmp_path / "data").glob("data_*.json"))
    assert not list((tmp_path / "reports").glob("report_*.html"))
    assert captured == [None]


def test_stop_logging_generate_report_true_invokes_callback_with_path(tmp_path):
    captured = []
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate,
                                  completion_callback=captured.append)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    c.stop_logging(completed_steps=1)            # generate_report defaults True
    assert len(captured) == 1 and captured[0] is not None
    assert captured[0].name.startswith("report_")


def test_log_metadata_forwards_to_ingestion_and_is_noop_without(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c.log_metadata({"Protocol Path": "<a>x</a>"})
    assert c._ingestion.metadata["Protocol Path"] == "<a>x</a>"
    c._ingestion = None
    c.log_metadata({"k": "v"})                   # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_controller.py -v"`
Expected: the three new tests FAIL — `TypeError: __init__() got an unexpected keyword argument 'completion_callback'` (and `stop_logging()` rejecting `generate_report`, and no `log_metadata`).

- [ ] **Step 3: Add the ctor kwarg + state**

In `controller.py`, replace the `__init__` (lines 52-59) with:

```python
    def __init__(self, *, settling_provider: Optional[Callable[[], float]] = None,
                 flush_scheduler: Optional[Callable[["ProtocolLoggingController"], None]] = None,
                 completion_callback: Optional[Callable[[Optional["Path"]], None]] = None):
        self._settling_provider = settling_provider or _default_settling_provider
        self._flush_scheduler = flush_scheduler or _qtimer_flush_scheduler
        self._completion_callback = completion_callback
        self._ingestion: Optional[LoggingIngestion] = None
        self._device_context = None
        self._step_idx = 0
        self._start_time = ""
        self._generate_report = True
```

Add `from pathlib import Path` to the imports at the top of the file (after `import time`):

```python
import json
import time
from pathlib import Path
from typing import Callable, Optional
```

(The `"Path"` forward-ref in the annotation then resolves; keeping it quoted is harmless.)

- [ ] **Step 4: Add the `log_metadata` forwarder**

Insert this method right after `attach` (after line 69, before `# --- lifecycle ---`):

```python
    def log_metadata(self, mapping) -> None:
        """Forward extra report metadata to the active run's ingestion.
        No-op when no run is logging (e.g. preview, or after flush)."""
        ing = self._ingestion
        if ing is not None:
            ing.log_metadata(mapping)
```

- [ ] **Step 5: Add the `generate_report` flag to `stop_logging`**

Replace `stop_logging` (lines 96-101) with:

```python
    def stop_logging(self, completed_steps, *, generate_report: bool = True) -> None:
        if self._ingestion is None:
            return
        self._generate_report = generate_report
        self._ingestion.log_metadata({"Completed Steps": completed_steps})
        _listener.clear_active_logger()
        self._flush_scheduler(self)
```

- [ ] **Step 6: Make `_flush` conditional + fire the callback**

Replace `_flush` (lines 103-119) with:

```python
    def _flush(self) -> None:
        ing = self._ingestion
        if ing is None:
            return
        report_path = None
        try:
            LoggingPersistence.write_data_files(
                self._device_context.experiment_directory, self._start_time,
                ing.entries, ing.columns)
            if self._generate_report:
                html = LoggingReport.build_html(
                    entries=ing.entries, columns=ing.columns, metadata=ing.metadata,
                    media=ing.media, device_context=self._device_context, notes=None)
                report_path = LoggingReport.write_report(
                    self._device_context.experiment_directory, html)
        except Exception as e:
            logger.error(f"protocol logging flush failed: {e}")
            report_path = None
        finally:
            self._ingestion = None
        # Notify the GUI (report saved / skipped). Outside the try so a
        # callback error is not misreported as a flush failure.
        if self._completion_callback is not None:
            try:
                self._completion_callback(report_path)
            except Exception as e:
                logger.error(f"logging completion callback failed: {e}")
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_controller.py -v"`
Expected: PASS (all tests in the file, including the pre-existing ones).

- [ ] **Step 8: Commit**

```bash
cd src && git add pluggable_protocol_tree/services/logging/controller.py pluggable_protocol_tree/tests/test_logging_controller.py
git commit -m "[logging] Optional report + completion callback + log_metadata forwarder (#421)"
```

---

## Task 2: Pane — wire the completion callback + success/preview dialogs

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py` (imports lines 22, 28-30; ctor lines 124-127)
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

- [ ] **Step 1: Write the failing tests**

Append to `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_on_logging_complete_shows_success_with_link(qapp, monkeypatch, tmp_path):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    seen = {}
    monkeypatch.setattr(ptp, "success", lambda **k: seen.update(k))
    report = tmp_path / "reports" / "report_x.html"
    report.parent.mkdir(parents=True)
    report.write_text("<html></html>", encoding="utf-8")

    pane._on_logging_complete(report)
    assert "report_x.html" in seen["message"]
    assert seen["title"] == "Run Summary Generated"


def test_on_logging_complete_none_shows_no_dialog(qapp, monkeypatch):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    calls = []
    monkeypatch.setattr(ptp, "success", lambda **k: calls.append(k))
    pane._on_logging_complete(None)
    assert calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k logging_complete -v"`
Expected: FAIL — `AttributeError: 'ProtocolTreePane' object has no attribute '_on_logging_complete'` (and `module ... has no attribute 'success'`).

- [ ] **Step 3: Extend the dialog import**

Replace lines 28-30 in `protocol_tree_pane.py`:

```python
from microdrop_application.dialogs.pyface_wrapper import (
    NO, YES, confirm, error as error_dialog, information, success,
)
```

- [ ] **Step 4: Add `QUrl` to the QtCore import**

Replace line 22:

```python
from pyface.qt.QtCore import Qt, QModelIndex, QTimer, Signal, QUrl
```

- [ ] **Step 5: Construct the controller with the completion callback**

Replace lines 124-127:

```python
        from pluggable_protocol_tree.services.logging.controller import (
            ProtocolLoggingController,
        )
        self.logging_controller = ProtocolLoggingController(
            completion_callback=self._on_logging_complete,
        )
        self.logging_controller.attach(self.executor.qsignals)
```

- [ ] **Step 6: Add the `_on_logging_complete` method**

Add this method to the class (place it just before `_on_new_experiment`, near line 1121, so the experiment-bar handlers stay grouped):

```python
    def _on_logging_complete(self, report_path):
        """Controller completion callback (runs on the GUI thread via the
        QTimer-scheduled flush). Shows the report-link success dialog when a
        report was generated; silent when it was skipped or the flush failed."""
        if report_path is None:
            return
        try:
            file_url = QUrl.fromLocalFile(str(report_path)).toString()
            success(
                parent=None,
                message=(f"Report file saved to:<br>"
                         f"<a href='{file_url}'>{Path(report_path).name}</a>"),
                title="Run Summary Generated",
            )
        except Exception as e:
            logger.warning(f"run-summary success dialog failed: {e}")
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k logging_complete -v"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd src && git add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "[dialogs] Wire logging completion callback + report-saved success dialog (#421)"
```

---

## Task 3: Pane — completion flow + outcome plumbing (finished / aborted / preview)

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py` (`_on_protocol_finished` ~570, `_on_protocol_aborted` ~581, `_on_protocol_terminated` ~583-613)
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

- [ ] **Step 1: Write the failing tests**

Append to `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def _pane_for_flow(monkeypatch, *, with_exp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from unittest.mock import MagicMock

    kwargs = {}
    if with_exp:
        kwargs = {"application": MagicMock(), "experiment_manager": MagicMock()}
        kwargs["experiment_manager"].auto_save_protocol.return_value = None
    pane = ptp.ProtocolTreePane([make_name_column()], **kwargs)
    pane.logging_controller = MagicMock()
    pane._current_run_preview_mode = False
    pane._repeats_completed = 2
    return ptp, pane


def test_completion_flow_finished_prompts_new_experiment(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    from unittest.mock import MagicMock
    pane._on_new_experiment = MagicMock()
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.YES)

    pane._run_completion_flow("finished")

    pane._on_new_experiment.assert_called_once()
    pane.logging_controller.stop_logging.assert_called_once_with(2, generate_report=True)


def test_completion_flow_aborted_no_skips_report(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.NO)

    pane._run_completion_flow("aborted")

    pane.logging_controller.stop_logging.assert_called_once_with(2, generate_report=False)


def test_completion_flow_error_prompts_summary_like_abort(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    monkeypatch.setattr(ptp, "confirm", lambda **k: ptp.YES)

    pane._run_completion_flow("error")

    pane.logging_controller.stop_logging.assert_called_once_with(2, generate_report=True)


def test_completion_flow_preview_shows_info_no_confirm(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=True)
    pane._current_run_preview_mode = True
    counts = {"info": 0, "confirm": 0}
    monkeypatch.setattr(ptp, "information",
                        lambda **k: counts.__setitem__("info", counts["info"] + 1))
    monkeypatch.setattr(ptp, "confirm",
                        lambda **k: counts.__setitem__("confirm", counts["confirm"] + 1) or ptp.YES)

    pane._run_completion_flow("finished")

    assert counts == {"info": 1, "confirm": 0}
    pane.logging_controller.stop_logging.assert_called_once_with(2)


def test_completion_flow_no_experiment_manager_skips_autosave_and_prompt(qapp, monkeypatch):
    ptp, pane = _pane_for_flow(monkeypatch, with_exp=False)
    confirms = []
    monkeypatch.setattr(ptp, "confirm", lambda **k: confirms.append(k) or ptp.YES)

    pane._run_completion_flow("finished")

    assert confirms == []          # no "Create New Experiment?" without a manager
    pane.logging_controller.stop_logging.assert_called_once_with(2, generate_report=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k completion_flow -v"`
Expected: FAIL — `AttributeError: 'ProtocolTreePane' object has no attribute '_run_completion_flow'`.

- [ ] **Step 3: Add the `_run_completion_flow` method**

Add this method directly after `_on_protocol_terminated` (after the method that ends around line 613):

```python
    def _run_completion_flow(self, outcome):
        """End-of-run UX: auto-save the protocol, prompt per outcome, and
        stop logging (which schedules the deferred flush). ``outcome`` is one
        of "finished", "aborted", "error". Every dialog is best-effort —
        failures are logged, never raised, so terminal cleanup is unaffected."""
        # Preview runs produce no artifacts; just confirm completion.
        if self._current_run_preview_mode:
            try:
                self.logging_controller.stop_logging(self._repeats_completed)
            except Exception as e:
                logger.warning(f"stop_logging (preview) failed: {e}")
            try:
                information(parent=None,
                            message="Preview run completed successfully.",
                            title="Preview Complete", timeout=3000)
            except Exception as e:
                logger.warning(f"preview-complete dialog failed: {e}")
            return

        have_exp = (self.experiment_manager is not None
                    and self.application is not None)

        # Auto-save the protocol + record its path into the report metadata,
        # before stop_logging so the metadata is present when _flush builds
        # the report.
        if have_exp:
            try:
                saved = self.experiment_manager.auto_save_protocol(
                    self.manager.to_json())
                if saved:
                    anchor = f'<a href="file:///{saved}">{saved.name}</a>'
                    self.logging_controller.log_metadata({"Protocol Path": anchor})
            except Exception as e:
                logger.warning(f"protocol auto-save failed: {e}")

        generate_report = True
        if outcome in ("aborted", "error"):
            try:
                if confirm(parent=None,
                           message=("Protocol was stopped before completion."
                                    "<br><br>Press <b>YES</b> to create run "
                                    "summary."),
                           title="Generate Run Summary?", cancel=False) == NO:
                    generate_report = False
            except Exception as e:
                logger.warning(f"run-summary confirm failed: {e}")
        elif outcome == "finished" and have_exp:
            try:
                if confirm(parent=None, title="Create New Experiment?",
                           cancel=False) == YES:
                    self._on_new_experiment()
            except Exception as e:
                logger.warning(f"new-experiment confirm failed: {e}")

        try:
            self.logging_controller.stop_logging(
                self._repeats_completed, generate_report=generate_report)
        except Exception as e:
            logger.warning(f"stop_logging failed: {e}")
```

- [ ] **Step 4: Thread `outcome` through `_on_protocol_terminated`**

Replace the signature line 583 `def _on_protocol_terminated(self):` with:

```python
    def _on_protocol_terminated(self, outcome="finished"):
```

Remove the existing logging-stop call (line 588):

```python
        self.logging_controller.stop_logging(self._repeats_completed)
```

(Delete that line — logging now stops inside `_run_completion_flow`.)

Then, at the **end** of `_on_protocol_terminated` (after the DV free-mode publish block that ends around line 613), append:

```python
        # Logging stop + end-of-run dialogs run last, after immediate teardown
        # (hardware clear / idle UI) so electrodes de-energize before any modal
        # dialog blocks. For "error", the caller (_on_error) runs the flow after
        # showing the error dialog, so we skip it here.
        if outcome != "error":
            self._run_completion_flow(outcome)
```

- [ ] **Step 5: Update the finished + aborted callers**

Line ~570, in `_on_protocol_finished`, change:

```python
        self._on_protocol_terminated()
```
to:
```python
        self._on_protocol_terminated("finished")
```

Line ~581, in `_on_protocol_aborted`, change:

```python
        self._on_protocol_terminated()
```
to:
```python
        self._on_protocol_terminated("aborted")
```

(Leave `_on_error`'s call as-is for now — Task 4 reworks it.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k completion_flow -v"`
Expected: PASS (all five `completion_flow` tests).

- [ ] **Step 7: Commit**

```bash
cd src && git add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "[dialogs] End-of-run completion flow (auto-save + new-experiment/summary prompts) (#421)"
```

---

## Task 4: Pane — error path shows error dialog, then prompts for summary

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py` (`_on_error` lines 378-398)
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

- [ ] **Step 1: Write the failing tests**

Append to `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_terminated_error_outcome_defers_completion_flow(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    ran = []
    pane._run_completion_flow = lambda outcome: ran.append(outcome)
    pane._on_protocol_terminated("error")
    assert ran == []                      # error: flow deferred to _on_error


def test_terminated_finished_outcome_runs_completion_flow(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    ran = []
    pane._run_completion_flow = lambda outcome: ran.append(outcome)
    pane._on_protocol_terminated("finished")
    assert ran == ["finished"]


def test_on_error_shows_dialog_before_completion_flow(qapp, monkeypatch):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    order = []
    pane._publish_protocol_running = lambda *a, **k: None
    pane._on_protocol_terminated = lambda outcome="finished": order.append(("term", outcome))
    pane._run_completion_flow = lambda outcome: order.append(("flow", outcome))
    monkeypatch.setattr(ptp, "error_dialog", lambda **k: order.append("error_dialog"))

    pane._on_error("boom")

    assert order == [("term", "error"), "error_dialog", ("flow", "error")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k 'terminated_ or on_error_shows' -v"`
Expected: `test_terminated_error_outcome_defers_completion_flow` and `test_on_error_shows_dialog_before_completion_flow` FAIL — current `_on_error` calls `_on_protocol_terminated()` (which, after Task 3, runs the flow for the default "finished" outcome) and never calls `_run_completion_flow("error")`.

- [ ] **Step 3: Rework `_on_error`**

Replace the body of `_on_error` (lines 378-398) with:

```python
    def _on_error(self, msg):
        logger.error(f"Protocol error: {msg}")
        self._publish_protocol_running("False")
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        # Immediate teardown only; the completion flow is deferred so the
        # error dialog is shown before the "Generate Run Summary?" prompt.
        self._on_protocol_terminated("error")
        # Present a nicely-formatted HTML body (rendered via the dialog's
        # `informative` slot) built from the structured StepExecutionError
        # fields, with the full traceback as collapsible detail. `message`
        # stays the plain summary as a fallback.
        exc = getattr(self.executor, "_error", None)
        informative = self._format_error_html(exc, str(msg))
        detail = None
        if exc is not None:
            import traceback
            detail = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        error_dialog(parent=None, title="Protocol error",
                     message=str(msg), informative=informative, detail=detail)
        # Now prompt for a run summary (error is treated like a force-stop).
        self._run_completion_flow("error")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k 'terminated_ or on_error_shows' -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd src && git add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "[dialogs] Error path: show error dialog, then prompt for run summary (#421)"
```

---

## Task 5: Full regression run

**Files:** none (verification only)

- [ ] **Step 1: Run the logging + pane suites together**

Run:
```bash
pixi run bash -c "cd src && python -m pytest \
  pluggable_protocol_tree/tests/test_logging_controller.py \
  pluggable_protocol_tree/tests/test_protocol_tree_pane.py \
  pluggable_protocol_tree/tests/test_logging_integration.py -v"
```
Expected: all PASS (naming the files explicitly bypasses the Redis-gated session skip).

- [ ] **Step 2: If green, no commit needed** — the work is complete and already committed per task.

---

## Self-Review

**Spec coverage:**
- Controller optional report + completion callback + `log_metadata` → Task 1. ✓
- Outcome plumbing (`finished`/`aborted`/`error`) → Task 3 (finished/aborted) + Task 4 (error). ✓
- Auto-save protocol + path metadata → Task 3, `_run_completion_flow`. ✓
- "Create New Experiment?" on finished → Task 3. ✓
- "Generate Run Summary?" on aborted/error, NO skips report → Task 3 (aborted) + Task 4 (error). ✓
- Preview info dialog → Task 3. ✓
- Report-saved success dialog after deferred flush → Task 2 (`_on_logging_complete` + callback wiring). ✓
- Graceful degradation when `experiment_manager`/`application` are None → Task 3 test + `have_exp` gate. ✓
- Error dialog shown before summary prompt → Task 4. ✓
- Tests for controller + pane → Tasks 1-4 each include tests; Task 5 regression. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the assertions. ✓

**Type/signature consistency:** `stop_logging(completed_steps, *, generate_report=True)`, `completion_callback(report_path|None)`, `log_metadata(mapping)`, `_run_completion_flow(outcome)`, `_on_protocol_terminated(outcome="finished")`, `_on_logging_complete(report_path)` — used identically across tasks and tests. Dialog calls use the verified `pyface_wrapper` signatures (`confirm(parent, message, title, cancel)`, `information(..., timeout=)`, `success(..., title=)`) and `YES`/`NO` constants. ✓
