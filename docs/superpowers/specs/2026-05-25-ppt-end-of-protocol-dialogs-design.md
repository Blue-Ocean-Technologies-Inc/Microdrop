# End-of-Protocol Dialogs for the Pluggable Protocol Tree — Design

**Date:** 2026-05-25
**Branch:** `feature/issue-421-protocol-data-logging` (extends PR #426)
**Related:** #421 (protocol data logging + report generation)

## Goal

Reproduce the legacy `protocol_grid` end-of-run user experience in the pluggable
protocol tree: auto-save the protocol, prompt for a new experiment or a run
summary, and surface the saved report file — all working with the pluggable
tree's **deferred settling flush** in `ProtocolLoggingController`.

## Background

In legacy `protocol_grid`, `ProtocolGridWidget.on_protocol_finished` runs a
synchronous sequence at the end of a run: auto-save the protocol, log its path
into the report metadata, stop logging, then (depending on whether the run was
force-stopped) prompt "Generate Run Summary?" or "Create New Experiment?",
generate the summary, and show a success dialog linking to the report.

The pluggable tree has no end-of-run dialogs today. `_on_protocol_terminated()`
only calls `self.logging_controller.stop_logging(self._repeats_completed)`. The
report is written by a **deferred** flush: `stop_logging` schedules `_flush`
after a settling delay (`QTimer.singleShot`), so the report file does not exist
synchronously when the run ends — the legacy "show the report link now" pattern
does not translate directly.

### Existing building blocks (already present, reused as-is)

- `microdrop_application.dialogs.pyface_wrapper`: `confirm`, `success`,
  `information` (project convention; never raw `QMessageBox`). `confirm` returns
  `YES` / `NO` constants.
- `experiment_manager.auto_save_protocol(protocol_data) -> Path | None` — writes
  `<exp>/protocols/protocol_<ts>.json`.
- `experiment_manager.initialize_new_experiment()` and the pane's
  `_on_new_experiment()` / dock pane `setup_new_experiment()`.
- `self.manager.to_json()` — the same protocol serialization the manual Save
  (Ctrl+S / `save_protocol_dialog`) uses.
- `LoggingReport.write_report(...) -> Path` already returns the report path.
- Three terminal callers converge on `_on_protocol_terminated()`:
  `_on_protocol_finished` (normal), `_on_protocol_aborted` (user stop),
  `_on_error` (execution error).

## Architecture

Three units change, each with a single responsibility.

### 1. `ProtocolLoggingController` — optional report + completion callback

The controller stays Qt-free, following its existing dependency-injection style
(`settling_provider`, `flush_scheduler`).

- **`stop_logging(completed_steps, *, generate_report=True)`** — stores the
  `generate_report` flag for the pending flush. Default `True` keeps existing
  callers (and tests) working.
- **`_flush`** — always writes the data JSON/CSV via `LoggingPersistence`.
  Writes the HTML report via `LoggingReport` **only when** `generate_report` is
  `True`. Captures the report `Path` (or `None`).
- **New injected `completion_callback: Optional[Callable[[Optional[Path]], None]]`**
  (constructor kwarg, default `None`). At the end of `_flush` (in a `finally`,
  after `self._ingestion` is cleared) it is called with the report `Path`, or
  `None` when the report was not generated or the flush raised. Because the
  default flush scheduler uses `QTimer.singleShot` on the GUI thread, the
  callback runs on the GUI thread and may show a dialog directly.
- **New `log_metadata(mapping)`** forwarder — forwards to
  `self._ingestion.log_metadata(mapping)` when an ingestion is active, else a
  no-op. Lets the pane add the auto-saved protocol path to the report metadata
  without reaching into the private `_ingestion`.

### 2. `ProtocolTreePane` — outcome plumbing + dialog flow

**Outcome plumbing.** `_on_protocol_terminated(outcome="finished")` gains an
`outcome` parameter, one of `"finished"`, `"aborted"`, `"error"`. The three
callers pass their outcome:

- `_on_protocol_finished` (only on the final repetition) → `"finished"`
- `_on_protocol_aborted` → `"aborted"`
- `_on_error` → `"error"`

`_on_protocol_terminated` keeps its existing immediate teardown (clear
highlights, idle button state, stop tick timer, merge phase controls, clear
hardware actuation, DV free-mode publish) running first and unconditionally for
all outcomes — independent of any dialog. It then delegates the logging-stop +
dialog sequence to a new `_run_completion_flow(outcome)`.

**`_run_completion_flow(outcome)`** — uses `pyface_wrapper` dialogs:

- **Preview run** (`self._current_run_preview_mode`): call
  `stop_logging(self._repeats_completed)` (a no-op in preview — no ingestion was
  created) and show `information("Preview run completed successfully.",
  title="Preview Complete", timeout=3000)`. No other prompts. Return.

- **Real run:**
  1. **Auto-save** (only when `experiment_manager` and `application` are both
     non-`None`): `path = experiment_manager.auto_save_protocol(self.manager.to_json())`.
     If `path`, record it into the run's report metadata as an HTML anchor
     (`<a href="file:///{path}">{path.name}</a>`) via
     `self.logging_controller.log_metadata({"Protocol Path": anchor})` — must
     happen *before* `stop_logging` so the metadata is present when `_flush`
     builds the report.
  2. **Branch on outcome:**
     - `"aborted"` or `"error"` (treated identically — both prompt for a
       summary): `confirm("Protocol was stopped before completion.<br><br>Press
       <b>YES</b> to create run summary.", title="Generate Run Summary?",
       cancel=False)`. `NO` → `generate_report = False`. For `"error"`, the
       structured error dialog (already built in `_on_error`) is shown **before**
       this confirm (see Error handling).
     - `"finished"`: `confirm(title="Create New Experiment?", cancel=False)`.
       `YES` → `self._on_new_experiment()` (the pane's own experiment-bar
       handler; the dock pane's `setup_new_experiment` merely delegates to it).
       Gated on `experiment_manager is not None`.
  3. `stop_logging(self._repeats_completed, generate_report=generate_report)`.

**`_on_logging_complete(report_path)`** — passed as the controller's
`completion_callback` at construction. When `report_path` is not `None`:
`success("Report file saved to:<br><a href='{file_url}'>{name}</a>",
title="Run Summary Generated")`, where `file_url = QUrl.fromLocalFile(
str(report_path)).toString()` (handles Windows backslashes). When `None`
(report skipped or flush failed), do nothing.

### 3. Wiring & graceful degradation

- The pane passes `completion_callback=self._on_logging_complete` when
  constructing `ProtocolLoggingController`.
- Experiment-related branches (auto-save, "Create New Experiment?") are gated on
  `self.experiment_manager is not None and self.application is not None`. Demos
  inject `None`, so those steps are skipped while the report/preview dialogs and
  the summary confirm still function.
- Every dialog / auto-save call is wrapped in `try/except` that logs a warning;
  a dialog or auto-save failure must never break the immediate teardown (which
  already ran) or leave the run in a bad state.

## Data flow

```
run ends
  -> _on_protocol_finished / _aborted / _on_error
       -> _on_protocol_terminated(outcome)
            -> immediate teardown (hardware clear, idle UI, timers)  [always]
            -> _run_completion_flow(outcome)
                 preview:  stop_logging(); information("Preview ...")
                 real:     auto_save_protocol -> metadata anchor
                           confirm (summary | new experiment) per outcome
                           stop_logging(generate_report=...)
                                -> [settling delay] -> _flush
                                     write data files (always)
                                     write report (if generate_report)
                                     completion_callback(report_path | None)
                                          -> _on_logging_complete
                                               success("Report saved ...")  [if path]
```

## Error handling

- `_on_error` currently calls `_on_protocol_terminated()` and then builds and
  shows the structured HTML error dialog. To present the error before asking
  about a summary, `_on_error` shows its error dialog **first**, then runs the
  completion flow (i.e. the error dialog precedes the "Generate Run Summary?"
  confirm). The immediate hardware/UI teardown still runs first, synchronously,
  so electrodes are de-energized regardless of how long the user lingers on the
  dialog.
- Auto-save, `confirm`, `success`, `information`, and `setup_new_experiment`
  calls are individually guarded; failures log a warning and are swallowed.
- The completion callback is invoked inside `_flush`'s `finally`; if report
  generation raised, the callback receives `None` and no success dialog appears
  (the error is already logged by the existing `_flush` except handler).

## Testing

**Controller (`test_*` for logging):**
- `stop_logging(generate_report=False)` → flush writes data JSON/CSV but no
  report file; `completion_callback` called once with `None`.
- `stop_logging(generate_report=True)` (default) → report written;
  `completion_callback` called once with the report `Path`.

**Pane (`test_protocol_tree_pane.py`, dialogs monkeypatched, fake
`experiment_manager`):**
- `outcome="finished"` → "Create New Experiment?" confirm shown; `YES` →
  `setup_new_experiment` invoked; `stop_logging` called with
  `generate_report=True`.
- `outcome="aborted"` + confirm returns `NO` → `stop_logging` called with
  `generate_report=False`; auto-save attempted.
- `outcome="error"` + confirm returns `YES` → error dialog shown before the
  summary confirm; `stop_logging` called with `generate_report=True`.
- `preview` run → `information` shown, no `confirm` calls, `stop_logging` called.
- `_on_logging_complete(path)` → `success` shown with the report link;
  `_on_logging_complete(None)` → no dialog.
- Graceful degradation: `experiment_manager=None` → no auto-save / no "Create
  New Experiment?" prompt, but preview/summary/report dialogs still run.

## Out of scope

- Changing the report content or the logging schema (covered by #421).
- The "recording active" warning dialog at protocol start (#398).
- Load-time protocol validation dialogs (#423).
- Per-column enable/disable for runs (#427).
