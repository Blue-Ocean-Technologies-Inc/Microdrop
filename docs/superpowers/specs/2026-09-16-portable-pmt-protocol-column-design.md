# Portable PMT protocol column — design

Issue #601, increment 2 (increment 1 = the PMT Capture pane, PR #686).
Epic #598. Branch `feat/601-pmt-protocol-column`, stacked on
`feat/601-portable-pmt-protocol` until #686 merges.

## Goal

A protocol step can carry a PMT capture setup: which spots to capture, each
spot's gain and exposure, and whether that spot is captured at the **start**
of the step, the **end**, or both. Running the protocol performs those
captures through the existing PMT capture routine and saves one CSV per spot,
tagged with the step.

## Decisions (from the maintainer, 2026-09-16)

| Question | Decision |
|---|---|
| When a step captures | **Per spot**: each spot row has a start tick and an end tick |
| How a setup gets into a step | **Pane follows step**: selecting a step loads its setup into the PMT Capture pane; edits there write straight into the step. No step selected → the pane works as today |
| Live stream running at a PMT step | **Stop the stream**, then capture (logged) |
| Avg / OSR / Rf | **Stored per step** with the spot table |

## Step cell value (contract)

One plain `Column`, id `pmt_capture`, in `portable_dropbot_protocol_controls`.
The cell holds a JSON-native dict, or `None` for "no PMT capture":

```json
{"avg": 16, "osr": 6, "rf_ohms": 499000.0,
 "entries": [{"slot": 2, "gain": 128, "exposure_s": 10.0,
              "at_start": false, "at_end": true}]}
```

Validated on read by a Pydantic `PmtStepCapture` model (extends
`PmtStreamSettings`; entries extend `PmtCaptureEntry` with `at_start` /
`at_end`) colocated in `portable_dropbot_controller/consts.py`. Parsing is
tolerant like the fluorescence `parse_chain`: an invalid cell logs a warning
and reads as no capture, never failing a protocol load. Entries with neither
tick are dropped on write. List order is capture order.

View: display-only summary, e.g. `3 spots · 1 start / 3 end`, blank for
`None`; `depends_on_row_traits = ["pmt_capture"]` because the pane writes the
cell over a topic.

## Step execution

`PmtCaptureHandler(BaseColumnHandler)`, `wait_for_topics = [PMT_CAPTURE_DONE]`.

- `on_pre_step` runs the entries ticked `at_start`; `on_post_step` those ticked
  `at_end`. Magnet/heater act in `on_step`, so a start capture is a baseline
  before the step's actions and an end capture reads the settled result.
- Skipped in preview mode, and when the phase has no ticked entries.
- Publishes `PMT_CAPTURE` with the step's avg/osr/rf and the phase's entries,
  plus three new optional request fields:
  - `request_id` = `f"{row.uuid}:{phase}"`, echoed back on `PmtCaptureDone`.
    The handler waits with `predicate=` matching it, so a pane-initiated
    capture or a stale done can never satisfy a step (the droplet-check
    `step_uuid` pattern).
  - `stop_live_stream: true`: the backend stops a running live stream (sets its
    stop event, joins its thread with a bound) before claiming, instead of
    refusing. Pane requests leave it false, so the pane keeps today's refusal.
  - `label`: a filename-safe step tag (e.g. `step1.2-end`), prefixed onto the
    CSV names and written into the CSV meta with `step_uuid` and `phase`.
- Timeout is computed per phase, not the column's scalar `ack_time_s`:
  `sum(exposure_s) + len(entries) × PMT_STEP_PER_SPOT_OVERHEAD_S + margin`
  (move ≤ 30 s, gain, stream start/stop). The scalar still gates fire-and-forget
  (`ack_time_s == 0` → publish and don't wait), like magnet/heater.
- `done.ok == False` raises with `done.error`, so the step fails like any
  unacknowledged hardware step. `AbortError` (Stop) publishes
  `PMT_CAPTURE_ABORT` before re-raising; the routine's own teardown powers the
  tube off.
- `on_post_protocol_end`: publish `PMT_CAPTURE_ABORT` unconditionally so an
  interrupted run never leaves a capture going.
- Priority: 20, the magnet/heater bucket (irrelevant across pre/post hooks, but
  keeps the column with its siblings).

## Pane follows step

In `portable_dropbot_status_and_controls` (PMT Capture pane):

- Subscribe the pane listener to `PROTOCOL_TREE_ROW_SELECTED`. A step selection
  loads the step's `pmt_capture` cell into the table: spot rows present in the
  cell take its gain/exposure/ticks and order; board spots absent from it are
  unticked. Avg/OSR/Rf load too. A group or no selection returns to **manual
  mode** (the table's own state, restored as it was).
- The table gains **Start** and **End** tick columns while a step is attached;
  in manual mode they are hidden and the existing Capture tick is used.
- Every table/settings edit while attached publishes
  `protocol_tree_set_cell_publisher` (`step_id`, `col_id="pmt_capture"`).
- Echo suppression by **value equality**, not a time window: remember the last
  value pushed for the attached step and ignore a `ROW_SELECTED` echo carrying
  exactly that value. Deterministic, unlike the fluorescence pane's
  `SELF_EDIT_ECHO_WINDOW_S`.
- A header line shows which step is attached ("Editing step 1.2" / "Manual").
- While a protocol runs, the pane's editing is disabled (the tree refuses
  set-cell during a run anyway); the capture progress, row highlight, countdown
  and results history all keep working for protocol captures, and a protocol
  run's frames are labelled with their step.

## Backend changes (`portable_dropbot_controller`)

- `PmtCaptureRequest`: optional `request_id: str = ""`, `label: str = ""`,
  `stop_live_stream: bool = False`.
- `PmtCaptureDone`: `request_id: str = ""` echoed (also on refusals).
- Capture claim: when `stop_live_stream` and the only blocker is the stream,
  stop it and wait for its teardown, then claim; log it.
- CSV filename: `pmt_<label>_spot<n>_<stamp>_gain<g>.csv` when a label is set;
  meta gains `request_id`, `label`.

## Tests (pure unit)

- Contract: `PmtStepCapture` round trip, tolerant parse, tick filtering.
- Column: summary text, `set_value` normalisation.
- Handler (fake ctx/publisher like `test_magnet_column.py`): start/end phase
  filtering, preview skip, request payload incl. `request_id`/`label`,
  predicate filters a foreign done, computed timeout, `ok=False` raises, abort
  publishes `PMT_CAPTURE_ABORT`.
- Mixin: `stop_live_stream` preempts a running stream; `request_id` echoed on
  done and refusal; labelled filenames.
- Pane: load a step's cell, manual-mode restore, edit pushes the set-cell
  payload, echo of own value ignored, foreign change reloads.

## Out of scope

- Reading results back into the protocol (e.g. branching on a PMT mean).
- A per-protocol summary report of all step captures (possible follow-up).
- Changing the fluorescence plugin.
