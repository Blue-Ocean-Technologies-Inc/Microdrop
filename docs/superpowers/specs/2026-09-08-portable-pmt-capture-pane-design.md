# Portable DropBot: PMT Capture pane — design

Date: 2026-09-08 · Issue: #601 (increment 1 of 2) · Depends on: #671 / PR #672
(re-vendored driver with `SignalBoardProxy.pmt_stream`).

## Goal

A dock pane on the portable instrument that lists the PMT spots the board is
configured with, lets the operator tick which spots to capture, set gain and
exposure per spot, order them, and run the capture routine now — one CSV per
spot plus a summary. No protocol-tree integration yet: that is increment 2,
which will attach the same table to a protocol step and run the routine at
step end.

## Decisions carried in from the brainstorm

- **Capture primitive: stream mode.** `SignalBoardProxy.pmt_stream(1, avg, osr)`
  starts a stream of unsolicited data frames on `CMD_PMT_STREAM_DATA` (0x123F);
  `pmt_stream(0, 0, 0)` stops it (idempotent). Exposure is therefore a plain
  duration. The buffered acquire (fixed ~10 s + ~8 s upload) is not used.
- **Spot identity comes from the board.** The motor board's `pmt_defaults`
  flash parameter (`_dp_pmt`) is a fixed array of five int32 Y-axis positions
  in µm, one per motor slot; `MotorBoardProxy.pmt_ctrl(slot)` moves to slot
  1..5. There are no names. A row is identified by its slot number and shows
  the slot's position. "Configured" = non-zero position (assumption, verified
  on the bench in the first test session — see Open questions).
- **The spot list is a published topic**, so a future add/remove-spot feature
  only has to republish it; the pane rebuilds its rows from whatever arrives.
- **Pane lives in `portable_dropbot_status_and_controls`**, next to the motors
  and calibration panes, using the same MVC trio + message handler + secondary
  dock pane base. Backend logic lives in `portable_dropbot_controller`'s PMT
  mixin. They talk over topics only.
- **Averaging / oversampling are fixed constants** for now (bench defaults),
  not table columns.

## Message contracts

All new constants live in `portable_dropbot_controller/consts.py`, with the
Pydantic payload models colocated so topic + schema are one importable
contract (published through `ValidatedTopicPublisher`). Existing constants
reused: `PMT_GAIN_BOUNDS`, `DEFAULT_PMT_GAIN`, `PMT_UPDATED`,
`PORTABLE_DROPBOT_CONNECTED/DISCONNECTED`.

New constants:

```python
#: Firmware slot count of the PMT position table (PMTPositionParams.pos).
PMT_SPOT_SLOTS = 5
#: Stream averaging / oversampling, the bench UI's defaults (avg=16 boxcar
#: samples per value; osr index 6 = 64x). Measured ~23 ms per value.
PMT_STREAM_AVG = 16
PMT_STREAM_OSR = 6
#: Exposure per spot in seconds (stream duration). At avg=16 the board
#: emits ~1 packet of 62 values per second, so the lower bound is set to
#: guarantee at least a few packets (a sub-second exposure would reliably
#: come back with "no stream frames received").
PMT_EXPOSURE_S_BOUNDS = (1.0, 600.0)
DEFAULT_PMT_EXPOSURE_S = 10.0
#: Counts -> volts -> amps, per the driver's PMT tab (2026-07-30 TIA rework):
#: ADS7076 16-bit, nominal 4.98 V reference (untrimmed, known), Rf 499 kΩ.
#: Gain is deliberately NOT folded in (it changes the tube's real output).
PMT_ADC_FULL_SCALE = 65536
PMT_VREF_V = 4.98
PMT_RF_OHMS = 499_000.0
#: Capture output: <experiment_directory>/captures/pmt/
PMT_CAPTURE_SUBDIR = "captures/pmt"
```

Topics:

| Constant | Topic | Direction | Payload |
|---|---|---|---|
| `PMT_SPOTS_READ` | `portable_dropbot/requests/pmt_spots_read` | pane → backend | `""` |
| `PMT_CAPTURE` | `portable_dropbot/requests/pmt_capture` | pane → backend | `PmtCaptureRequest` |
| `PMT_CAPTURE_ABORT` | `portable_dropbot/requests/pmt_capture_abort` | pane → backend | `""` |
| `PMT_SPOTS_UPDATED` | `portable_dropbot/signals/pmt_spots_updated` | backend → pane | `PmtSpotsUpdated` |
| `PMT_CAPTURE_PROGRESS` | `portable_dropbot/signals/pmt_capture_progress` | backend → pane | `PmtCaptureProgress` |
| `PMT_CAPTURE_DONE` | `portable_dropbot/signals/pmt_capture_done` | backend → pane | `PmtCaptureDone` |

Payload models (Pydantic, in `consts.py`):

```python
class PmtSpot(BaseModel):
    slot: int              # 1..PMT_SPOT_SLOTS, the pmt_ctrl argument
    position_um: int       # PMTPositionParams.pos[slot - 1]

class PmtSpotsUpdated(BaseModel):
    spots: list[PmtSpot]   # configured slots only, ascending slot order

class PmtCaptureEntry(BaseModel):
    slot: int
    gain: int              # PMT_GAIN_BOUNDS
    exposure_s: float      # PMT_EXPOSURE_S_BOUNDS

class PmtCaptureRequest(BaseModel):
    entries: list[PmtCaptureEntry]   # capture order = list order, ticked only

class PmtCaptureProgress(BaseModel):
    index: int             # 0-based position in the request
    total: int
    slot: int
    stage: str             # "move" | "gain" | "stream" | "saved" | "failed"
    detail: str = ""       # e.g. "12/60 packets", the error text on "failed"

class PmtSpotResult(BaseModel):
    slot: int
    gain: int
    exposure_s: float
    n_samples: int
    mean_counts: float
    sd_counts: float
    min_counts: int
    max_counts: int
    csv_path: str = ""     # empty when no samples were written
    error: str = ""

class PmtCaptureDone(BaseModel):
    ok: bool               # every entry captured and saved
    aborted: bool
    directory: str         # the captures/pmt folder used
    results: list[PmtSpotResult]
    error: str = ""        # request-level failure (refused, not connected)
```

The existing `PMT_UPDATED` signal keeps carrying `acquiring: bool`; the capture
routine publishes `acquiring=True` at start and `False` at the end so the More
Controls PMT group greys its own Acquire button while a capture runs, exactly
as it does for the single acquire today.

## Backend (`portable_dropbot_controller`)

### Pure helpers — `portable_dropbot_controller/pmt_capture.py` (new, Qt-free, no driver import)

Ported from the driver repo's `full_test_ui/tabs/pmt_tab.py` so the CSVs are
interchangeable with the bench UI's, and unit-testable without hardware:

- `StreamAssembler` — feeds raw 0x123F payloads (`[pkt_idx u16 LE][n u16 LE]
  [n × u16 LE]`), tracks the absolute packet index across u16 wraps (a
  backwards step > 0x8000 is a wrap; a smaller one is a duplicate/aliased
  frame and is dropped, counted in `duplicates`), keeps `samples`, per-sample
  absolute index, and `(abs_idx, arrival_monotonic)` per packet. Thread-safe
  (`feed` runs on the transport RX thread).
- `calibrate_period(assembler, avg) -> (period_s, source)` — measured packet
  cadence when ≥ 2 packets and within [0.25×, 10×] of the `avg/1000`
  estimate, else the estimate; `source` is `"measured"` or `"estimated"`.
- `capture_stats(samples) -> (n, mean, sd, min, max)`.
- `write_capture_csv(path, samples, times_s, meta) -> int` — `#`-prefixed
  `key=value` preamble, then `index,t_s,counts,volts,amps`; volts and amps
  derived from `meta["adc_full_scale"]`, `meta["vref_v"]`, `meta["rf_ohms"]`.
  Streams rows, never joins them.
- `capture_filename(slot, gain, now) -> "pmt_spot{slot}_{YYYYmmdd-HHMMSS}_gain{gain}.csv"`.
- `decode_pmt_positions(reply_bytes) -> list[int]` — the `GET_PARAMS` reply is
  `key NUL blob`; the blob is five big-endian int32 (the vendored
  `PMTPositionParams` layout, decoded here with `struct` so the helper stays
  driver-free).

### PMT mixin — `services/portable_dropbot_pmt_mixin_service.py`

New handlers beside the existing power / gain / acquire ones:

- `on_pmt_spots_read_request` — `self.proxy.uart.getBoardParameter("motor",
  "pmt_defaults")` under `_proxy_call`; decode; publish `PmtSpotsUpdated`
  with the non-zero slots. Log a warning naming all five raw values when none
  is non-zero (the bench check for the "configured" rule).
- `on_pmt_capture_request` — validates the payload; when a capture is already
  running or the payload is empty it publishes `PmtCaptureDone(ok=False,
  error=…)` straight away so the pane's `capturing` flag never sticks, and
  otherwise runs the
  routine below **inline in the handler** (like the calibration macro and the
  DropBot self tests). Dramatiq's worker pool lets the abort request run on
  another thread meanwhile.
- `on_pmt_capture_abort_request` — sets the running capture's
  `threading.Event`; the routine finishes its teardown and reports
  `aborted=True`.

Capture routine, per request:

1. Resolve `directory = <app_globals["experiment_directory"]>/captures/pmt`,
   create it. Publish `PMT_UPDATED {acquiring: true}`.
2. Once: fluorescence LED off (`uart.setLEDIntensity(0, fluorescence=True)`,
   belt-and-braces — the firmware dark-chambers during a stream too), then
   `sig.pmt_power(1)`; read both boards' UIDs for the CSV preamble
   (best-effort, `"unavailable"` on failure).
3. For each entry in order — every step publishes `PmtCaptureProgress`:
   - `move`: `motor.pmt_ctrl(slot)` (blocking, driver timeout 30 s).
   - `gain`: `sig.pmt_gain_set(gain)`.
   - `stream`: subscribe `uart.subscribe(CMD_PMT_STREAM_DATA, assembler.feed)`
     **before** `sig.pmt_stream(1, PMT_STREAM_AVG, PMT_STREAM_OSR)`; wait
     `exposure_s` in 50 ms slices watching the abort event; `sig.pmt_stream(0,
     0, 0)`; unsubscribe. A `None` reply from stream start means BUSY or
     timeout → this entry fails.
   - `saved`: calibrate the period, compute stats, write the CSV, append a
     `PmtSpotResult`. A failed step records `error` on the result, skips the
     rest of that entry, and continues with the next (the run report should
     say which spot failed, not stop at it); an abort stops after the current
     entry's teardown.
4. Teardown, unconditional and in independent `try` blocks so one failure
   cannot skip the next: `sig.pmt_stream(0, 0, 0)` (idempotent), `sig.pmt_power(0)`
   (a failure here is logged at error level — the tube may still be powered),
   `self._apply_light_intensity()` (restores the pane's illumination setpoint,
   as the existing acquire macro does), `uart.unsubscribe(CMD_PMT_STREAM_DATA)`.
   The motor is left where it is; homing at protocol end is increment 2's job.
5. Publish `PmtCaptureDone` and `PMT_UPDATED {acquiring: false}`; log the
   directory and each CSV path at info level.

Locking: **per command, not per routine.** Each driver call goes through
`_proxy_call` (which takes `_proxy_lock`), and the lock is released during
the timed stream wait so the 2 s status poll keeps the status pane live over a
multi-minute capture. Stream frames arrive on the transport's RX thread via
the subscriber regardless of the lock. (The existing single-acquire macro holds
the lock for its whole ~10 s; this routine can run for minutes, which is why it
differs.)

CSV preamble keys: `source=Microdrop portable PMT capture`, `taken` (ISO),
`slot`, `position_um`, `gain`, `exposure_s`, `avg`, `osr`, `adc_full_scale`,
`vref_v`, `rf_ohms`, `mcu_uid`, `motor_uid`, `sample_period_s`,
`effective_rate_hz`, `period_source`, `samples_per_packet`, `n_samples`,
`packets`, `duplicate_packets`, `duration_s`, `aborted`, `error`.

## Frontend (`portable_dropbot_status_and_controls`)

### `consts.py`

`PMT_CAPTURE_LISTENER = f"{PKG}_pmt_capture_listener"` and its
`ACTOR_TOPIC_DICT` entry: `PORTABLE_DROPBOT_CONNECTED`,
`PORTABLE_DROPBOT_DISCONNECTED`, `PMT_SPOTS_UPDATED`, `PMT_CAPTURE_PROGRESS`,
`PMT_CAPTURE_DONE`.

### `models/pmt_capture_model.py` (Qt-free)

```python
class PmtSpotRow(HasTraits):
    #: Motor slot (1-based) — the identity of the row.
    slot = Int
    #: Slot position on the PMT Y axis, from the board.
    position_um = Int
    #: "Spot 3 · 24.50 mm" — read-only ID column.
    label = Property(Str, observe="slot, position_um")
    capture = Bool(True)
    gain = Range(*PMT_GAIN_BOUNDS, DEFAULT_PMT_GAIN)
    exposure_s = Range(*PMT_EXPOSURE_S_BOUNDS, DEFAULT_PMT_EXPOSURE_S)

class PortableDropbotPmtCaptureModel(BaseStatusModel):
    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE
    rows = List(Instance(PmtSpotRow))
    selected_row = Instance(PmtSpotRow)
    capturing = Bool(False)
    progress = Str("-")
    results_directory = Str("")
    start_button = Button("Start capture")
    abort_button = Button("Abort")
    refresh_button = Button("Refresh spots")

    def merge_spots(self, spots):      # spots: list of (slot, position_um)
    def capture_entries(self):         # ordered ticked rows as dicts
```

`merge_spots` is the row-sync rule: rows are keyed by slot; existing rows keep
their capture/gain/exposure and their position in the list (position_um is
refreshed); slots not seen before are appended in ascending slot order with
defaults; rows whose slot is gone are dropped. Called on every
`PMT_SPOTS_UPDATED`, including the reconnect one, so a reconnect never resets
the operator's settings. `capture_entries` returns the ticked rows in table
order. Both are pure and unit-tested.

### `controllers/pmt_capture_controller.py`

`@observe` one-liners: `start_button` → `pmt_capture_publisher.publish(
entries=self.model.capture_entries())` after setting `capturing=True` and
`progress="starting…"` (refuse with a status line, no publish, when no row is
ticked); `abort_button` → `PMT_CAPTURE_ABORT`; `refresh_button` →
`PMT_SPOTS_READ`.

### `views/pmt_capture_view.py`

Module-level TraitsUI `View`:

- `Item("rows", editor=TableEditor(columns=[ObjectColumn(name="label",
  label="Spot", editable=False), CheckboxColumn(name="capture"),
  ObjectColumn(name="gain"), ObjectColumn(name="exposure_s", label="Exposure
  (s)", format="%.1f")], reorderable=True, show_toolbar=True, sortable=False,
  deletable=False, selected="selected_row"), show_label=False)` — the toolbar's
  move up / move down buttons act on the selected row; the whole table is
  `enabled_when="connected and not capturing"`.
- `HGroup(UItem("start_button", enabled_when="connected and not capturing and
  rows"), UItem("abort_button", enabled_when="capturing"),
  UItem("refresh_button", enabled_when="connected and not capturing"))`.
- `Item("progress", style="readonly")`, and `results_directory` as a readonly
  item (a clickable link is a follow-up; the path is also logged).

The view is instantiable standalone: `PortableDropbotPmtCaptureModel(rows=[…])
.edit_traits(view=PmtCaptureView)` renders the table with no plugin scaffolding.

### `message_handlers/pmt_capture_message_handler.py`

`BaseMessageHandler` subclass: `_on_connected_triggered` sets `connected` and
publishes `PMT_SPOTS_READ` (pull-on-connect, as the calibration handler does);
`_on_pmt_spots_updated_triggered` → `model.merge_spots`;
`_on_pmt_capture_progress_triggered` → `progress = f"Spot {slot} ({index+1}/
{total}): {stage} {detail}"`; `_on_pmt_capture_done_triggered` → `capturing =
False`, `results_directory`, and a summary line ("3/3 spots saved to …" or
"FAILED: spot 2 — <error>" / "aborted after n spots").

### `dock_panes.py` / `plugin.py`

`PortableDropbotPmtCaptureDockPane(PortableDropbotSecondaryDockPane)`, id
`PKG + ".pmt_capture_dock_pane"`, name `"PMT Capture"`, wired like the
calibration pane and contributed from the plugin alongside it.

## Testing (hardware-free, pure pytest)

- `portable_dropbot_controller/tests/test_pmt_capture.py`: `StreamAssembler`
  ordering, u16 wrap, duplicate rejection; `calibrate_period` measured vs
  estimated (plausibility window); `write_capture_csv` preamble + column
  round-trip via `csv`/`pandas.read_csv(comment="#")`; `decode_pmt_positions`
  on a synthetic reply; Pydantic model validation of every payload.
- `portable_dropbot_status_and_controls/tests/test_pmt_capture_model.py`:
  `merge_spots` keeps settings and order, appends new slots, drops vanished
  ones; `capture_entries` honours ticks and order.

The routine itself is bench work, tracked by the checklist below. Standard
verification for touched files stays compile + ruff.

## Bench checklist (first session on the rig)

- [ ] `PMT_SPOTS_READ` reply: note the five raw positions; confirm unused slots
      read 0 (else adjust the "configured" rule) and the µm scale matches the
      motors pane's PMT position readback.
- [ ] Spot count on this rig (the pane should show the configured ones; you
      expect 4).
- [ ] One-spot capture at 2 s: CSV appears under `captures/pmt`, row count ≈
      exposure / sample_period, `period_source=measured`.
- [ ] Three-spot capture with a reorder: files land in table order; progress
      line advances per stage.
- [ ] Abort mid-stream: teardown log shows stream stop + power off; partial
      CSV for the current spot; `aborted=true`.
- [ ] Status pane keeps updating during a 60 s exposure (lock released).
- [ ] More Controls' Acquire button is greyed during a capture.

## Out of scope (later increments / issues)

- Protocol column, attach-to-step sync, run-report contribution, homing at
  protocol end — increment 2 of #601.
- Add / remove / re-teach spots (writes `pmt_defaults`) — future; only the
  republish hook exists.
- Filter-wheel position per spot; avg/OSR in the UI; a clickable results link.

## Open questions

1. Meaning of an unused slot in `pmt_defaults` (0 assumed).
2. Whether the firmware refuses `pmt_ctrl` while the PMT is powered or a
   stream is open (the routine stops the stream before the next move, so this
   only matters for error text).
3. Whether the fluorescence-LED-off + illumination-restore choreography is
   still wanted with the firmware's own dark-chamber handling; kept for parity
   with the existing acquire macro.
