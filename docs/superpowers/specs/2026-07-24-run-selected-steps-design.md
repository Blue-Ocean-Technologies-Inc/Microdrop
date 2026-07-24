# Run Selected Steps — design (issue #558)

Status: approved 2026-07-24
Branch: `feat/558-run-single-step-option-in-protocol-tree`
Scope: `src/pluggable_protocol_tree/`

## Problem

The protocol tree can only run the whole protocol, or (via the current
selection) run *from* a step to the end — `ProtocolExecutor.start()` already
takes `start_step_path`. Operators developing a protocol want to exercise a
subset: one step, several steps, a group, or a mixed selection, without
running everything around it.

## User-facing behaviour

Select one or more rows in the protocol tree, right-click, choose **Run
Selected Steps** (or press **Ctrl+R**). Only the selected rows execute.

The run is an ordinary run in every other respect: Preview Mode and the
"Repeat Protocol" spinbox both apply, logging and the run summary happen, the
active-row highlight and device-viewer sync behave as usual.

## Selection semantics

Each selected row becomes an **independent execution root**:

- Paths that are descendants of another selected path are dropped — a selected
  group already covers its children.
- Roots execute in tree order.
- A row's **own** `repetitions` apply. Repetitions of ancestors *outside* the
  selection do not.

```
Wash (reps=3)
├─ Step A
└─ Step B          select B     -> B                     (1 frame)
                   select Wash  -> A,B,A,B,A,B           (6 frames)

Step C (reps=4)    select C     -> C,C,C,C               (4 frames)
```

This falls out of *re-rooting* the frame expansion at each selection root,
rather than filtering the full frame list. Filtering would have preserved
ancestor repeats, which is the behaviour we explicitly rejected.

A selection that yields no frames (nothing selected, or only empty groups) is
not runnable: the menu entry is disabled and the shortcut is a no-op.

## Architecture

### Scope lives in two places only

`RowManager.iter_execution_frames(scope_paths=None)` — absent means today's
whole-protocol walk; present means re-root at each normalized selection root.
`iter_execution_steps(scope_paths=None)` mirrors it. One public entry point,
backwards-compatible with every existing caller.

`ProtocolExecutor.run_paths` — a public trait, set by `start(run_paths=...)`
and cleared when the run terminates. `_run_steps` sources its `frames` list
from it. Everything downstream in the executor (step index/total, the pause
cursor, mid-run seek resolution, the active-row highlight) already works off
that list, so no other executor logic changes.

The executor is the single source of truth for the active scope. No component
stores a second copy.

### Status counter

`ProtocolStatusController` already holds an `executor` reference, so it reads
the scope from there rather than keeping a copy. Two of its four
`manager.iter_execution_*` call sites pass `executor.run_paths` through:
`_distinct_steps` (which `_count_steps` and `_step_index_of` both build on) and
`_next_name`. During a subset run the status bar reads "Step 2/3"; a full run
is unchanged.

`_row_at` and `_frame_index_for_rep` stay **unscoped**. `_row_at` is a pure
path lookup — scoping it would only make previewing an out-of-scope step
return None. `_frame_index_for_rep` maps timeline cells to executor frame
indices, and the timeline renders the full protocol (see Out of scope), so
scoping one half of that mapping would make it inconsistent with itself.

The dock pane's logging `n_steps_provider` gets the same treatment so the run
log records the subset size, not the protocol size.

### UI wiring

`views/tree_widget.py` owns the menu entry and the shortcut. It does not know
the executor exists — it emits `run_selected_requested(list)` carrying the
path tuples. `ProtocolTreePane` relays the signal alongside its existing
`selection_changed`. `dock_pane._on_run_selected` re-checks
`_is_protocol_active()` and calls `_start_protocol_run(preview_mode=...,
run_paths=scope)`.

Ctrl+R is gated on `_structural_editable`, exactly like the existing Ctrl+G /
Ctrl+Shift+G fold shortcuts, so it is dead during a run. The context menu is
already suppressed entirely while running. With the dock pane's guard that is
three independent barriers against starting a subset run over a live one.

No shortcut clash: the tree's only other bindings are Ctrl+G, Ctrl+Shift+G,
and the copy/cut/paste standards; quick actions use bare letter keys.

## Files touched

| File | Change |
|---|---|
| `models/row_manager.py` | `scope_paths` argument; selection-root normalizer |
| `execution/executor.py` | `run_paths` trait; `start(run_paths=)`; frame source |
| `services/protocol_status_controller.py` | scope-aware step counts and lookups |
| `views/tree_widget.py` | menu entry, Ctrl+R, `run_selected_requested` |
| `views/protocol_tree_pane.py` | signal relay |
| `views/dock_pane.py` | `_on_run_selected`; scoped `n_steps_provider` |

## Out of scope

The timeline bar keeps rendering the **full** protocol during a subset run. The
playhead lands on the correct rows but visibly skips the unselected ones —
arguably the right affordance, since you can see what is being skipped.
Scoping the timeline is separate work.

## Tests

Targeted, not exhaustive:

- `test_row_manager.py` — selection-root normalization; the own-reps rule;
  descendant-of-selected dropping; tree ordering across mixed depths; empty
  scope vs `None`.
- `test_executor.py` — `run_paths` honoured; step totals reported against the
  subset; `repeats` loops the scoped sequence; scope cleared on terminate.
- `test_run_selected.py` (new) — the widget's runnability guard, emitted
  roots, and the run-lock on the keyboard path.
- `test_protocol_status_controller.py` — step counts follow the active scope.

Note for whoever runs these: the suite needs Redis up, or directory-level
collection skips wholesale. `test_protocol_tree_pane.py` carries ~100
pre-existing failures (it still expects `pane.executor`, which moved to the
dock pane in #471) and `test_executor.py` three more; those are unrelated to
this work and were verified failing on the untouched branch first.
