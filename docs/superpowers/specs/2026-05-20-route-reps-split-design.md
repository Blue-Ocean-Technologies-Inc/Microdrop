# Route-Reps Split — Design

**Date:** 2026-05-20
**Topic:** Disambiguate "Reps" (whole-thing repeat) from route-loop repetition in the pluggable protocol tree, and turn the duration-mode flag into a true internal row trait.

## Problem

`repetitions` ("Reps") is currently consumed in **two** unrelated places:

1. `row_manager._expand_frames` — execution-order expansion. A **step** yields its
   `on_step` `N` times; a **group** expands its child subtree `N` times.
2. `phase_math.iter_phases(n_repeats=repetitions)` — route-loop sizing. Loop routes
   run `N` cycles; open routes run `N` passes when `linear_repeats` is on.

So a step with `Reps = 2` **and** routes plays its routes **4×** (2 step expansions ×
2 route cycles) — an accidental `Reps × Reps`. The two meanings need to be separated.

Separately, `repeat_duration_controls` ("Dur Controls") is a hidden checkbox column
that only exists to serialize an internal mode flag. It should not be a user-facing
column at all.

## Decisions (confirmed with user)

- **"Reps" repeats the whole thing, everywhere.** Keep `repetitions` driving
  `_expand_frames` unchanged (step re-runs `on_step` N×; group repeats subtree N×).
  Stop feeding `repetitions` into `iter_phases`.
- **New "Route Reps" column** (`route_repetitions`) feeds `iter_phases`' `n_repeats`.
  On a step, total route plays = `Reps × Route Reps`. Ignored on groups.
- **"Repeat (s)" → "Route Reps Dur"** (display rename only; `col_id` stays
  `repeat_duration`). Becomes visible (was hidden).
- **Keep the modal flag + confirm-dialog handoff**, but repointed to arbitrate
  **Route Reps ↔ Route Reps Dur** (not the whole-thing "Reps").
- **`repeat_duration_controls` becomes a plain `Bool` row trait**, removed from the
  column system, with a bespoke persistence hook so it still round-trips.
- **Route Reps Dur padding:** complete `floor(T / cycle_time)` full cycles, then hold
  the last phase's electrodes actuated for the exact leftover `T − cycles×cycle_time`,
  so total step time lands on `T` precisely.
- **No load-time migration.** `route_repetitions` defaults to `1`; old protocols whose
  steps relied on `repetitions` for route looping will loop routes 1× until the user
  sets Route Reps. Documented behavior change.

## Column model after the change

| col_id | Display | Visible | Editable on | Drives |
|---|---|---|---|---|
| `repetitions` | Reps | yes | step + group | `_expand_frames` only (whole-thing repeat) |
| `route_repetitions` *(new)* | Route Reps | yes | step (inert on group) | `iter_phases` `n_repeats` |
| `repeat_duration` *(renamed display)* | Route Reps Dur | yes (was hidden) | step | duration budget |
| `linear_repeats` | Lin Reps | hidden | step | open-route replay gate (paired with `route_repetitions`) |
| ~~`repeat_duration_controls`~~ | — | **removed as column** | — | now a plain `Bool` row trait |

`col_id`s for `repeat_duration` and `linear_repeats` are unchanged so saved protocols
still load. `route_repetitions` is the only genuinely new column.

## Components & changes

### 1. `models/row.py`
Add `repeat_duration_controls = Bool(False)` to `BaseRow` (inherited by both the
step and group dynamic subclasses; only meaningful on steps, harmlessly `False` on
groups). Import `Bool` from `traits.api`.

### 2. `services/persistence.py` — bespoke flag round-trip
The serialized format is positional (`fields = [depth, uuid, type, name, *col_ids]`,
`first_value_idx = 4`). To avoid shifting that tuple (clipboard `_serialize_selection`,
`_field_index`, and old-file loading all assume index 4), persist the flag in a new
top-level **uuid-keyed map**, mirroring the existing `protocol_metadata` pattern:

- `serialize_tree`: add `"row_flags": {uuid: {"repeat_duration_controls": bool}}`,
  emitting an entry only for rows where the flag is `True` (keep saves compact).
- `deserialize_tree`: after building each row, set
  `row.repeat_duration_controls = row_flags.get(uuid, {}).get("repeat_duration_controls", False)`.
  Missing key (old files) → `False`.

`RowManager.to_json` / `from_json` / `set_state_from_json` already delegate to these
functions; no signature change needed.

**Known limitation:** clipboard copy/paste (`_serialize_selection` / `_paste_from_payload`)
is column-based and will not carry the flag — a pasted step lands in count mode. Acceptable
for this scope; noted for a possible follow-up.

### 3. `builtins/repeat_duration_controls_column.py` — delete
Remove the file, its import, and its entry in `plugin._assemble_columns`. (Demos already
omit it.)

### 4. `builtins/repetitions_column.py` — drop the dialog
Remove `RepetitionsHandler` (and its confirm-dialog). "Reps" becomes a plain
`RepsSpinBoxColumnView` (keep the group-editable override). No handler ⇒ default
write-through. The reps↔duration dialog logic moves to Route Reps (§5).

### 5. `builtins/route_repetitions_column.py` — new
- `RouteRepetitionsColumnModel`: `Int(1, desc=...)`, `col_id="route_repetitions"`,
  `col_name="Route Reps"`, `default_value=1`.
- View: visible `IntSpinBoxColumnView(low=1, high=1000)`. Editable on steps; the base
  `IntSpinBoxColumnView` already strips editability on groups, which matches "inert on
  group".
- `RouteRepsHandler`: the relocated count-side handoff. If `row.repeat_duration_controls`
  is `True`, prompt (Switch/Cancel) to hand control back from duration; on Switch set
  `row.repeat_duration_controls = False` then write; on Cancel reject. Otherwise plain
  write-through. (Same logic as today's `RepetitionsHandler`, reading the flag from the
  row trait instead of a column.)

### 6. `builtins/repeat_duration_column.py` — rename + visible + repoint
- `col_name="Route Reps Dur"` (id unchanged).
- View becomes the visible `DoubleSpinBoxColumnView(low=0.0, high=3600.0, decimals=2,
  single_step=0.1)` (drop the `Hidden…` mixin).
- `RepeatDurationHandler`: unchanged structure, but the auto-estimate now reads
  `route_repetitions` instead of `repetitions` for `n_repeats`, and the flag is read/set
  on `row.repeat_duration_controls` (the trait).

### 7. `services/phase_math.py` — duration mode + padding
- `_route_with_repeats`: in the loop-route duration branch
  (`repeat_duration_s > 0 and step_duration_s > 0`), **do not append the trailing
  `cycle[0]` return phase**, so the emitted phase count = `cycles × cycle_phases` and
  the dwell sums to exactly `cycles × cycle_time`. (Count mode keeps the return phase.)
  Keep `cycles = max(1, floor(...))` — if `T < cycle_time`, run one full cycle
  (overshoot, pad = 0).
- New pure helper `pad_seconds_for_duration(routes, trail_length, trail_overlay, *,
  repeat_duration_s, step_duration_s) -> float`: returns
  `max(0.0, repeat_duration_s − cycles × cycle_time)` for the dominant loop route
  (`cycle_length = max` of loop-route window counts, matching
  `effective_repetitions_for_duration`), else `0.0`. Returns `0.0` when no loop routes,
  `repeat_duration_s <= 0`, or `step_duration_s <= 0`.
- `iter_phases`' signature is unchanged; callers pass `n_repeats=route_repetitions`.

### 8. `builtins/routes_column.py` — feed Route Reps + hold-pad
- `RoutesHandler.on_step`: pass `n_repeats=int(getattr(row, "route_repetitions", 1))`
  to `iter_phases` (was `repetitions`).
- After the phase loop, if `bool(getattr(row, "repeat_duration_controls", False))` and
  `repeat_duration > 0`, compute `pad = pad_seconds_for_duration(...)` and, when
  `pad > 0`, `_cooperative_sleep(pad, stop_event, pause_event)` **without publishing a
  new state** — the last phase's electrodes remain actuated ("hold last phase"). Then
  set `ctx.scratch[DURATION_CONSUMED_KEY] = True` as today.

### 9. `plugin.py` — column list
Add `make_route_repetitions_column()` (place it right after `make_repetitions_column()`
or adjacent to `make_repeat_duration_column()`); remove the
`make_repeat_duration_controls_column` import and list entry. `make_repeat_duration_column`
stays (now visible).

### 10. Demos
`run_widget.py`, `run_session_demo.py`, `run_headless.py`, `run_widget_auto.py`: add
`make_route_repetitions_column()` to each column list (they already omit the controls
column). They get `repeat_duration_controls` for free as a row trait.

## Execution semantics summary

**Step, count mode** (`repeat_duration_controls = False`):
`Reps` step re-runs × (`Route Reps` route cycles + 1 return phase per loop route).

**Step, duration mode** (`repeat_duration_controls = True`, `Route Reps Dur = T > 0`):
per step run: `floor(T / cycle_time)` full cycles (no return phase) + hold last phase for
`T − cycles×cycle_time` ⇒ each run takes exactly `T`. Outer `Reps` still multiplies whole runs.

**Group:** `Reps` repeats the subtree; `Route Reps` / `Route Reps Dur` are inert.

## Data flow (duration mode, one step run)

```
RoutesHandler.on_step
  phases = iter_phases(..., n_repeats=route_repetitions,
                       repeat_duration_s=repeat_duration, ...)
        -> _route_with_repeats: cycles = max(1, floor(T/cycle_time)), NO return phase
  for phase in phases: publish + wait_for(applied) + dwell(duration_s)
  if repeat_duration_controls and repeat_duration > 0:
      pad = pad_seconds_for_duration(...)
      if pad > 0: _cooperative_sleep(pad)      # hold last electrodes
  ctx.scratch[DURATION_CONSUMED_KEY] = True
```

## Error handling / edge cases

- `T < cycle_time` → one full cycle, `pad = 0` (preserves current `max(1,…)` safety).
- No loop routes (open-only) → `pad_seconds_for_duration` returns 0; duration mode has no
  budgeting effect, matching today.
- `step_duration_s <= 0` → `pad = 0` (no division).
- Stop/Pause during the pad sleep: handled by `_cooperative_sleep`'s existing
  stop/pause checks.

## Testing (manual run by user per project preference — do not auto-run pytest)

- `test_phase_math.py`: duration-mode return-phase removal; new `pad_seconds_for_duration`.
- `test_builtins.py`: `route_repetitions` column present; `repeat_duration_controls` no
  longer a column.
- `test_hidden_columns.py`: `repeat_duration` now visible; controls column gone.
- `test_persistence.py`: `row_flags` round-trip; field-index expectations after column
  set change; old-file (no `row_flags`) loads with flag `False`.
- `test_routes_handler_redis.py` / `test_executor*`: Route Reps drives loop count; hold-pad
  timing.
- `test_plugin.py`, `test_compound_persistence.py`, `test_session.py`: updated column set.

## Conventions

Follow `microdrop-conventions` (Traits/TraitsUI models, f-strings, existing column
factory pattern). Dialogs continue via `microdrop_application.dialogs.pyface_wrapper`
(already used by the handlers).
