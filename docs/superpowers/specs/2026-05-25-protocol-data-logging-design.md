# Protocol Data Logging for the Pluggable Protocol Tree — Design

**Date:** 2026-05-25
**Issue:** [#421](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/421) (PPT-10.6)
**Topic:** Build a protocol data logger + report generator for the pluggable protocol tree, modeled on the legacy `protocol_grid/services/protocol_data_logger.py` but designed fresh and decoupled from any widget.

## Problem

The legacy `ProtocolDataLogger` (768 LoC, coupled to `protocol_grid.widget.PGCWidget`) produces every experiment artifact MicroDrop makes today: per-step capacitance traces, force calculations, columnar data exports (JSON + CSV), and an HTML report with plotly heatmaps and per-channel plots. The new pluggable protocol tree has **no equivalent** — runs leave no on-disk artifacts. This builds one for the new tree, hooked into the new `ProtocolExecutor` lifecycle signals (no widget coupling).

## Decisions (confirmed with user)

1. **Packaging:** plain `HasTraits`/service code under `pluggable_protocol_tree/services/logging/`, wired in the dock pane to `executor.qsignals`. Not a separate plugin.
2. **Structure:** split into single-responsibility units — **Ingestion**, **Persistence**, **Reporting** — behind a thin **`ProtocolLoggingController`** that the executor signals drive.
3. **Output contract:** keep the legacy artifact set + report layout + the force formula. Downstream tooling depends on it; redesign is out of scope.
4. **Settling preference:** reuse the existing `protocol_grid.preferences.ProtocolPreferences().logs_settling_time_s` (default 3.0s) now; re-point if #419 (PPT-10.4) later relocates it.
5. **Device context** (experiment dir, device SVG path, electrode areas, electrode→channel map, capacitance-per-unit-area) is **assembled by the dock pane** and handed to the controller at run start — the controller stays decoupled from the device viewer.

## Architecture & components

New package `pluggable_protocol_tree/services/logging/`:

### `controller.py` — `ProtocolLoggingController`
The only unit that knows about the executor. Lives on the GUI thread; driven by Qt signals.

- `attach(qsignals)` — connect to `protocol_started`, `step_started`, `protocol_finished`, `protocol_aborted`, `protocol_error`.
- `start_logging(device_context: LoggingDeviceContext, n_steps: int, preview_mode: bool)` — no-op when `preview_mode` is True; otherwise creates a fresh `LoggingIngestion`, records start metadata, registers itself as the active capacitance/actuation/media sink.
- on `step_started(row)` → set the ingestion's current step (`step_id=row.uuid`, `step_idx`). The actuation (channels/area) is **not** set here — it tracks per phase (see Data flow).
- `stop_logging(completed_steps)` — records final metadata, unregisters the sink, then schedules the settling flush: `QTimer.singleShot(int(logs_settling_time_s * 1000), self._flush)`.
- `_flush()` — calls `LoggingPersistence.write_data_files(...)` then `LoggingReport.write_report(...)`; all failures caught + logged.
- `log_capacitance(payload)` / `set_actuation(electrodes, channels)` / `log_media(model)` / `update_capacitance_per_unit_area(value)` — thin forwards to the active ingestion (called by the listener; thread-safe via the ingestion lock).

### `ingestion.py` — `LoggingIngestion`
Collects rows of data. No Qt, no broker.

- `set_step(*, step_id, step_idx)` — set the current step (from `step_started`).
- `set_actuation(*, actuated_channels, actuated_area)` — set the current **phase** actuation (from each `ELECTRODES_STATE_CHANGE`). Carries forward until the next phase; not reset on step boundary.
- `update_capacitance_per_unit_area(value: float | None)`.
- `log_capacitance(message)` — parse the JSON payload `{capacitance, voltage, instrument_time_us, reception_time}` (tolerating "123.45pF"/"100V" and bare-number forms), compute force, append one columnar entry stamped with the current step **and current phase actuation**. Skips when no step set or unparseable (legacy parity).
- `log_media(model: MediaCaptureMessageModel)` — bucket into video/image/other.
- `log_data(dict)` / `log_metadata(dict)` — append data row / merge metadata; track column order.
- `_calculate_force(voltage)` — `0.5 * capacitance_per_unit_area * voltage**2`, rounded 6dp; `None` when c-per-area is `None` or `voltage <= 0`.
- Append paths take a `threading.Lock` (capacitance arrives on a worker thread; step-context updates on the GUI thread).
- Read accessors: `entries`, `columns`, `metadata`, `media`.

Data-entry columns (legacy contract): `step_idx`, `utc_time`, `instrument_time_us`, `step_id`, `Capacitance (pF)`, `Voltage (V)`, `Force Over Unit Area (mN/mm^2)`, `Actuated Area (mm^2)`, `actuated_channels`.

### `persistence.py` — `LoggingPersistence`
Pure functions over the collected entries.

- `to_columnar(entries, columns) -> {"columns": [...], "data": [[...], ...]}`.
- `write_data_files(experiment_dir, start_time, entries, columns) -> (json_path, csv_path)`:
  - JSON → `experiment_dir/data/data_<start_time>.json` (columnar shape).
  - CSV → `experiment_dir/data/data_<start_time>.csv` (via pandas).
  - Applies the uint32 rollover correction to `instrument_time_us` (same as legacy `save_data_file`).

### `reporting.py` — `LoggingReport`
Pure function `build_html(entries, metadata, media, device_context, notes) -> str` + `write_report(experiment_dir, html) -> path` → `experiment_dir/reports/report_<timestamp>.html`. Sections (legacy parity): metadata, data-files links, data summary (per-numeric-column mean/std/min/max), data trends (per-step plotly bar charts with error bars), device heatmap (channel actuation duration via `create_plotly_svg_dropbot_device_heatmap` using `device_context.device_svg_path`), media captures (embedded video/image), notes. Plotly via CDN; self-contained HTML.

### `capacitance_listener.py`
A dramatiq listener subscribing to:
- `CAPACITANCE_UPDATED` (`dropbot/signals/capacitance_updated`) → `controller.log_capacitance(payload)`.
- `ELECTRODES_STATE_CHANGE` → `controller.set_actuation(electrodes, channels)` — the per-phase actuation snapshot (this is exactly what `RoutesHandler` publishes once per phase, immediately before the hardware applies it, so the capacitance that follows is attributed to the right phase).
- the media-capture topic (`DEVICE_VIEWER_MEDIA_CAPTURED`) → `controller.log_media(...)`.

Forwards each payload to the **active** controller via a module-level registry the controller sets in `start_logging` and clears in `stop_logging` (mirrors the executor's active-step pattern). Registered in the tree plugin's `ACTOR_TOPIC_DICT`. Because messages for these topics are processed in arrival order, the most-recent `ELECTRODES_STATE_CHANGE` is the phase a subsequent capacitance sample belongs to.

### `LoggingDeviceContext` (value object, in `controller.py` or a small `models.py`)
Static per-run device state assembled by the dock pane:
- `experiment_directory: Path`
- `device_svg_path: Path | None`
- `channel_areas: dict[int, float]` (channel → area mm², from the device viewer's `electrodes.channel_electrode_areas_scaled_map`; used to sum a phase's actuated area from `ELECTRODES_STATE_CHANGE.channels`)
- `capacitance_per_unit_area: float | None` (seed; live updates flow via `update_capacitance_per_unit_area`)

## Lifecycle & data flow

```
dock pane: build ProtocolLoggingController, controller.attach(executor.qsignals)
run start →
  pane assembles LoggingDeviceContext (experiment dir from application/experiment_manager;
      svg path + electrode areas + map from the device-viewer model; c-per-area seed)
  protocol_started → controller.start_logging(ctx, n_steps, preview_mode)
                     (registers active sink; no-op if preview)
  step_started(row) → step_idx += 1; ingestion.set_step(step_id=row.uuid, step_idx)
  ELECTRODES_STATE_CHANGE (per phase, via listener) →
                      actuated_channels = msg.channels
                      actuated_area     = Σ channel_areas[ch] for msg.channels
                      ingestion.set_actuation(actuated_channels, actuated_area)
  CAPACITANCE_UPDATED (via listener) → controller.log_capacitance(payload)
                      → ingestion stamps it with the current step + current phase
                        actuation + force
  media topic → controller.log_media(MediaCaptureMessageModel)
  calibration signal → controller.update_capacitance_per_unit_area(value)
  protocol_finished/aborted/error → controller.stop_logging(completed_steps)
       → QTimer.singleShot(settling_ms) → _flush(): persistence.write_data_files(); report.write_report()
```

**Per-phase attribution:** each capacitance sample is attributed to the phase that was actuated when it arrived — `actuated_channels` / `actuated_area` track the most-recent `ELECTRODES_STATE_CHANGE` (one per phase), while `step_id` / `step_idx` track the current step. This is finer-grained than the legacy per-step logging: a route step that walks many electrodes records the actual per-phase actuation rather than one step-wide set.

## Device context sourcing

The dock pane is the single place that gathers device state (it already holds the device-viewer sync + application references). It builds `LoggingDeviceContext` at run start and passes it into `start_logging`. The controller, ingestion, persistence, and reporting units never import the device viewer or `protocol_grid.*`.

`capacitance_per_unit_area` (a dropbot calibration snapshot) is fed live through the listener/controller. The implementation plan pins the exact source the legacy used (the dropbot capacitance/calibration topic or `app_globals`); this is a graceful-degradation input — when it is unavailable, `_calculate_force` returns `None` and every other artifact is still produced (legacy parity), so its precise wiring does not block the rest of the logger.

## Threading, preview, errors

- Controller is GUI-thread (Qt signals). The capacitance/media listener runs on a dramatiq worker; ingestion guards its append paths with a lock.
- Preview mode → `start_logging` no-ops; no artifacts, no sink registration (legacy parity).
- All ingestion/persistence/reporting failures are caught and logged — a logging fault must never crash or abort a protocol run.
- Settling: `stop_logging` defers the flush by `logs_settling_time_s` so in-flight capacitance messages after "done" are still captured.

## Testing

- **Unit (no Qt/broker):**
  - Ingestion: capacitance parsing (pF/V and bare forms, invalid skipped), force formula, step + per-phase actuation stamping (a sample after `set_actuation(A)` then `set_actuation(B)` records B's channels/area), media bucketing, column-order tracking.
  - Persistence: columnar round-trip, `instrument_time_us` rollover correction, JSON + CSV written.
  - Reporting: `build_html` returns HTML containing each expected section; empty-data and no-media cases don't crash.
- **Integration:** run a protocol through `ProtocolExecutor` (preview off) feeding `ELECTRODES_STATE_CHANGE` (≥2 phases with different electrode sets) and capacitance samples into the controller; assert the artifact set exists (`data/data_*.json`, `data/data_*.csv`, `reports/report_*.html`), the data file has the expected columns, and samples are attributed to the correct phase's `actuated_channels`.

## Acceptance criteria (from #421)

- [ ] Spec under `docs/superpowers/specs/` (this document).
- [ ] New service(s) in `pluggable_protocol_tree/services/logging/`; no `from protocol_grid.*` imports **except** the settling preference (`ProtocolPreferences`) per decision 4.
- [ ] Hooked into `ProtocolExecutor` lifecycle signals; no widget coupling.
- [ ] Same artifact set as legacy (columnar data file + CSV + HTML report) on a real run.
- [ ] Preview-mode runs skip logging.
- [ ] Capacitance ingestion subscribes via the standard pub/sub topic.
- [ ] Media-capture ingestion handles `MediaCaptureMessageModel`.
- [ ] Force calculation uses the legacy formula `0.5 · C_per_unit_area · V²`.
- [ ] Tests pass; manual smoke produces a readable HTML report.

## Out of scope

- Redesigning the artifact format / report layout (keep legacy contract).
- Deleting the legacy `ProtocolDataLogger` in place (that's PPT-9 / #371).
- Cloud / remote upload of artifacts.
- Relocating `logs_settling_time_s` out of `protocol_grid` (that's #419).
