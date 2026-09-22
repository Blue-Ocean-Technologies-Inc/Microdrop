# Wide path demo

A testbed for **wide paths**: a route drawn on the device plus a slug shape
— extra lanes to the left and right of the route, and the usual trail
length / overlay along it — and the rules for what happens to that slug at a
corner. The rules were settled by the corner-turning game (2026-09-09) and
are pinned by the tests; the demo lets you draw a route and step through
the phases the rules produce.

## Running it

From `microdrop-py/`:

```
pixi run python -m examples.demos.wide_path_demo.run [device.svg]
```

Redis is not needed (ignore the connection noise in the console). The
bundled 2x3 device loads by default; pass a device SVG path to use another.

The window opens with one empty path selected:

- **Draw** — click, or drag across, neighbouring electrodes. Revisiting an
  electrode is allowed, so loops, knots and back-and-forth work as in the
  device viewer. **Undo last** drops the last electrode; **Clear route** or
  Esc empties it. **Invert** reverses the route, and **Merge with next**
  joins it to the path below at a shared endpoint — the device viewer's own
  invert and merge, whose `Route` is likewise an ordered list of ids with
  segments derived from it (`merged` in the geometry module). A click on a non-neighbour is refused and says so in the
  status line.
- **Slug** — a lane frame (**Left / right** of travel, or **In / out** of
  the turn, so lanes hug the outer rung whichever way the route bends), the
  two lane counts, Trail / Overlay, **Rotation lock**
  (translate without rotating; squares do this regardless; on by default,
  as is the In / out frame), **Soft start** (the block comes on a row at a
  time), **Soft end** (drain to the last electrode after the route ends) and,
  once the route is
  closed by clicking its first electrode again, **Repeats**: how many times
  the loop plays before returning onto its start.
- **Phases** — `<` / `>` step one phase at a time, the timeline bar (the
  protocol tree's own) seeks by click or drag, the frame panel shows the
  current phase in notation, and the canvas fills it in white. The slug's
  whole footprint is tinted blue, the route yellow.

Tests (pure, no GUI, no Redis), from `src/`:

```
../.pixi/envs/default/python.exe -m pytest examples/demos/wide_path_demo/tests -q
```

## The rules

Execution only ever asks one question — *which electrodes are on at each
phase* — and `wide_path_geometry.slug_phases` answers it. Which rule
applies depends only on the slug's shape, `W = left + right + 1` across
and `T = trail_length` along:

| shape | rule |
|---|---|
| `W = 1` | the trail is the route itself: the shipped trail algorithm, bent corners included, byte-for-byte unchanged |
| route shorter than `T` | hold: everything the slug would cover comes on as one phase and stays on |
| `W = T` (a square) | a square never notices a corner: a rigid footprint that only translates. It hangs behind its head along the way it travels and is centred across it, so it starts on the first electrode and ends on the last; before a turn it slides on until centred on the corner electrode, then runs along the new leg |
| rotation lock (any shape) | the same mechanism on demand: the block keeps the orientation it started with and only translates, so a `3x2 r` reads `2x3 u` after the turn. The **Rotation lock** checkbox in the Slug box; `rotation_lock=True` in `slug_phases` |
| anything else | a `W x T` block hung behind its head along the heading it arrives by, re-hung at every turn — a one-step jog included. With no trail the corner electrode shows both orientations: its arriving row, then its departing row (its own phase, with the lanes of the leg it departs onto, so a lane never swings across the route in one phase), before the slug moves on |
| loop (first electrode repeated last) | the device viewer's definition. The cycle plays `repetitions` times and then runs on far enough for the block to sit at its first position again, so the slug ends where it began (the shipped return phase). The run is one unrolled route (`unroll`) and every rule above applies to it unchanged: the start electrode is arrived at too, so a loop opening on a corner turns there, and strides carry straight through the seams. The shipped trail restarts its stride at every lap instead; the two agree whenever the stride divides the cycle. Phase heads index the unrolled route |

A block phase advances `T - overlay` route electrodes. A translating block
advances by its own extent along the leg it is on minus the overlay: `T` on
legs parallel to its original heading, `W` across them, so a locked `3x1 r`
going down strides like a `1x3 d` and the overlay runs up to
`max(W, T) - 1`. Its steps never cross a corner: it reaches the corner,
slides on until it is centred on the corner electrode, then strides off
along the new leg; a cross leg that ends the route runs until the block's
leading edge is the last electrode, so nothing sticks out past the end
(a loop's last electrode is its start again and keeps the start position).
Across a leg it travels far enough to arrive
in the lanes the next leg wants: on a hairpin in the in / out frame the
lanes mirror across the route, so the run is the leg plus the lane shift and
the block slides on past the leg's last electrode rather than jumping
across the route at the next corner. A
locked `2x1` (in 0, out 1) on a one-electrode down leg therefore moves two
down: in one phase at overlay 0, in two at overlay 1
(`translating_positions`).

**Clipping and the actuation count.** Electrodes that do not exist (beyond
the device edge, inside a reservoir neck) are left out of a block; nothing is
faked in their place. Instead the actuation count stays constant: a clipped
block is topped up with the device electrodes nearest where its unclipped
centre would be, distance along the heading costing more than across it, so a
wall shifts the slug sideways and only a neck stretches it
(`top_up_to_centre`). A slug born against an edge is full from its first
phase. Once every phase is known, a topped-up phase whose neighbours already
share the overlay, with the head moving no further than the stride, is dropped
(`trim_wraps`). The count only comes down at the end of the route, and only
with **Soft end** on: the block's rows go off one per phase from its tail,
down to the head row (`ramp_down`). **Soft start**
is the mirror at the other end: before the first full phase the rows come on
one per phase from the tail (`ramp_up`). Both are the shipped ramps, which add or
drop one route electrode at a time, done a row at a time — for a width-1
trail they are exactly the shipped `#`, `##`, `###` and back, and width-1
routes get the shipped ones. A held short route does not ramp at the start.
A clipped tail counts by rows too: the 2x2 that enters the neck holding four
cells drops its two-cell tail row first, then the next (4, 2, 1), where the
maintainer's drawing of 2026-09-10 went cell by cell (4, 3, 2, 1).

Every shipped trail feature now has a slug counterpart; what is still open
is moving this out of the sandbox, next to the shipped algorithm in
`microdrop_utils/route_execution.py`.

## Notation

Frames are one character per lattice cell over a fixed window, actuations
only: `.` off, `#` on, `_` no electrode there. A frame is titled
`<phase number> <heading>` — `3 u` is the third phase, travelling up — with
headings as letters r / l / u / d as seen on screen. A slug is
`WxT <heading>`, e.g. `3x2 r`: width across the heading, trail along it, so
the picture follows from the letter and the numbers never change at a
corner.

```
3 r            4 u
. . # .        . . . .
. . # .        . # # # .
. . # .        . . . .
```

## Vocabulary

- **route** — the electrode ids the user drew, in travel order; each a
  neighbour of the previous. A **loop** is a route whose first electrode is
  repeated last (click the start again to close it); its **cycle** is the
  route without that repeat, and the loop **unrolls** into the route it
  actually plays.
- **slug** — the body of liquid the route drives: one contiguous block of
  electrodes, not "a route with lanes". The functions compute what the slug
  does, hence `slug_phases`.
- **phase** — the shipped word for the set of electrodes on at one moment of
  a step (`PathExecutionService.calculate_trail_phases_for_path`); the new
  function returns the same kind of thing under the same name so it can slot
  in beside the old one.
- **head** — the route electrode a phase is anchored on; reads against
  "trail", which the sidebar already uses.
- **block** — one phase's `W x T` rectangle. The **footprint** is the union
  of every block the slug ever occupies.
- **heading** — a unit vector for the direction of travel. The heading *at* a
  route electrode is the direction the route arrives by; the first electrode
  takes the direction it leaves by. That is why a corner electrode still
  belongs to the incoming leg.
- **lane** — a signed offset across the heading: positive to the screen-left
  of travel, negative to the screen-right, 0 on the route.
- **lane frame** — how the two lane counts are read. Left / right: screen
  sides of travel. In / out: inside / outside of the turn. The outside at a
  corner is its convex side, opposite the turn; a straight electrode borrows
  the nearest corner ahead of it (so a whole leg agrees with the turn it
  approaches), or the last corner behind it after the final turn; a route
  with no corner regresses to left / right (in = left, out = right).
  `outer_sides` decides the side per electrode, `lane_counts` resolves the
  counts. A translating block (square, or rotation-locked) reads its lanes
  across the heading it started with, so in this frame `lane_counts` mirrors
  them to whichever side of that axis the outside lies on: a locked `3x1`
  with in 0 / out 2 rides above the outbound leg of a hairpin and slides
  below the return leg, never rotating.
- **pitch** — the centre-to-centre spacing of the electrode array, the
  standard term (pixel pitch, pin pitch, electrode pitch); unambiguous where
  "spacing" is not. `lattice_pitch` because it is *inferred* from the
  neighbour graph (median neighbour distance, so oversized reservoir
  electrodes cannot skew it) and then used as the spacing of the idealised
  grid the blocks are laid on.
- `left`, `right`, `trail_length`, `trail_overlay` keep the sidebar's names.
  `width` is never stored — it is always `left + right + 1`.

## The code

Read it bottom-up.

### `microdrop_utils/wide_path_geometry.py` — pure functions, no traits, no Qt

The geometry and the notation live in `microdrop_utils` (integration step 1,
2026-09-11), with their tests and the answers file beside them in
`microdrop_utils/tests`; the demo imports them from there.

The module is a pipeline, top to bottom; each section answers one question.

**Lattice** — where things are.

| function | decides |
|---|---|
| `lattice_pitch(centroids, neighbours)` | the grid spacing (median neighbour distance) |
| `unit`, `left_normal`, `axis` | vector helpers. `left_normal` is **the only place** the SVG y-down convention lives: `(1, 0)` → `(0, -1)`. `axis` rounds a heading onto the lattice axes so a real device's slightly-off centroids compare equal. |
| `nearest_electrode(point, centroids, pitch)` | the closest centroid within `SNAP_TOLERANCE` (½ pitch), or `None` — a hole. Snapping, not neighbour-walking, is what makes one code path work on a synthetic grid and a real SVG. |

**Route** — the line the slug follows.

| function | decides |
|---|---|
| `route_headings(route, centroids, cycle_length=0)` | one heading per electrode: arriving direction, leaving direction for the first (arriving too on an unrolled loop) |
| `leaving_heading(headings)` | the first leg's heading — what a translating block is aligned with |
| `turns_at(index, headings)` | whether the route changes direction at an electrode |
| `is_loop(route)`, `unroll(route, repetitions, trail_length)` | the device viewer's loop rule (first electrode repeated last) and the route a loop actually plays: its cycle N times plus the return onto the start |

**Lanes** — which side each lane count goes to.

| function | decides |
|---|---|
| `outer_sides(route, centroids, headings=None)` | +1 / −1 per electrode: the convex side of the nearest corner ahead, else the last corner behind, else screen-right |
| `lane_counts(headings, sides, left, right, lane_frame, translating)` | `(left, right)` per electrode. Left / right: as typed. In / out: the outside count on the outer side — swapped per electrode for a re-hung block, mirrored across the block's own axis for a translating one |

**Blocks** — the electrodes one placement covers.

| function | decides |
|---|---|
| `block_cells(anchor, heading, left, right, trail_length, centroids, pitch)` | the W x T block whose leading cell sits on `anchor` and hangs behind it along `heading`; every position snapped, holes dropped |
| `block_footprint(head_id, ...)` | the same with a route electrode as the leading cell |

**Positions** — where the block sits at each phase. Both schedules return
`Position(head, anchor, heading, lanes)`, one per phase; `slug_phases`
turns each into cells with one `block_cells` call.

| function | handles |
|---|---|
| `rehung_positions(route, headings, lanes, T, overlay, centroids)` | the block that re-hangs at every turn: heads at `T - 1` then every `T - overlay`, ending on the last electrode, the stride ignoring corners; a bar adds the departing row on a corner |
| `translating_positions(route, headings, lanes, T, overlay, centroids, pitch, closed)` | the block that keeps its heading (squares, rotation lock): hung behind the head on along legs; slides to centre on the corner electrode; one straight run across a leg, striding `W - overlay`, into the lanes the next leg wants (past the leg's end if they mirror) or, on a final leg, until its leading edge is the last electrode; loops keep their start position |
| `stride_of`, `run_points` | the stride for an extent and overlay; the anchor points of a straight run every stride, always ending on the finish |

**Phases** — the answer.

| function | handles |
|---|---|
| `trail_phases(route, T, overlay, soft_terminate, soft_start)` | the shipped algorithm on the route itself — width-1 behaviour |
| `hold_phase(route, headings, lanes, centroids, pitch)` | a route shorter than its trail: one phase, the union of 1-deep blocks at every electrode |
| `top_up_to_centre(ids, centre, heading, reuse, target, centroids, neighbours, pitch)` | clipping: a short block topped up with the electrodes nearest its unclipped centre, touching the slug |
| `trim_wraps(phases, wrapped, overlay, stride, neighbours)` | drops topped-up phases that only filled time, without a gap or a longer stride |
| `rows_along`, `ramp_up`, `ramp_down` | the block's rows across a heading; soft start brings them on tail first, soft end takes them off the same way |
| `slug_phases(route, centroids, neighbours, left, right, T, overlay, pitch=None, rotation_lock, soft_terminate, lane_frame, repetitions, soft_start)` | the dispatcher: unroll a loop → headings → width 1 to `trail_phases` → lanes → hold if short, else positions from one of the two schedules → cells, `top_up_to_centre`, drop repeats, `trim_wraps` → ramps |

Every phase is a `Phase(head, heading, ids)`: the route index it belongs
to, the direction of travel there, and the electrodes on. Phases are simply
numbered by position, from 1, as the shipped executor numbers them; the
notation prints that number and the heading letter as a frame's title.

### `microdrop_utils/wide_path_notation.py` — pictures

`lattice_cells` (centroid → grid cell, rounded), `render_frame`,
`window_around`, `render_phases` (one shared window so frames line up;
titles from each phase's number and heading), `parse` (frame → cells, for tests),
`shorthand`, `frame_text` (side by side, for printing).

### `wide_path.py` — `WidePathModel`, one path

Inputs → `@observe` handlers → outputs, all plain traits:

- inputs the user owns: `electrode_polygons`, `electrode_neighbours`,
  `name`, `route_ids` (source of truth), `left`, `right`, `trail_length`,
  `trail_overlay`; `note` fires when `pick` refuses.
- `_device_changed` (polygons or neighbours) derives `centroids` and
  `pitch`, then recomputes.
- `_recompute` (route or shape) writes `phases`, `footprint_ids`,
  `summary` — straight from `slug_phases`.
- `pick`, `undo`, `clear` are the only mutators.

### `models.py` — `WidePathDemoModel`, the testbed

Same pattern one level up. `selected` is a real `Instance` trait kept by
`_selection_changed` from `selected_index`/`paths` — a Property cannot be
traversed by observers, an Instance can, so `@observe("selected.phases")`
works. `editing` is the selected path or a spare instance, only so hidden
sidebar Items always have something to bind to. `_phase_view_changed`
derives `phase_titles`, `max_step`, `phase_label`, `frame`, `summary` and
clamps `step`. `_note_fired` observes `selected:note` — colon, because a dot
would fire on selection change with the path object as `event.new`.

### The rest

- `controller.py` — Buttons → calls, device loading, prev/next. Computes
  nothing.
- `canvas.py` — the one Qt widget: paints footprint, route and current
  phase; turns clicks and drags into `pick`.
- `timeline.py` — the protocol tree's `TimelineBar`, driven by a bridge
  that observes `phase_titles` and `step`.
- `view.py` — declarative TraitsUI; slug Items bind through
  `object.editing.*`.
- `tests/` — `test_wide_path_model.py` covers the observer chains, headless.
  The geometry's own tests sit beside it in `microdrop_utils/tests`:
  `test_wide_path_slug_phases.py` runs the 36 game picks in
  `wide_path_answers.json` (route, lattice, shape, expected phases) on the
  synthetic grid and on the bundled 2x3 device captured as
  `wide_path_device_2x3.json`, plus rule-level tests;
  `test_wide_path_geometry.py` covers the helpers and the notation. Change a
  pick in the JSON and the test names the rule that broke.
