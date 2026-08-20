# Branching protocol flowchart — standalone UX demo

A self-contained prototype for testing one idea: **the protocol's flow is
drawn graphically on a node canvas, while the table only sets step
parameters.** Column providers contribute *Decision* objects (a question +
possible answers with default routes); the user places them as shapes from
a step's ＋ palette, wires their outcomes to other steps — or combines
outcomes through an AND operator — and at run time the clicked answer
sends execution down the drawn edge (or the provider default when nothing
was drawn).

The canvas look and interactions follow the
`claude/protocol-controls-branching-xuhkrc` branch's flow view
(`pluggable_protocol_tree/views/flow_graph_dialog.py`): dark theme, slim
node slabs, obstacle-avoiding routed edges, snap-to-node glow, the
"＋ New step" ghost on blank-space drops, group/ungroup, Ctrl+wheel zoom
and middle-mouse pan.

## Run it

From the repo root (needs only PySide6 — no redis, dramatiq, envisage,
traits, or hardware):

```
python -m examples.demos.branching_flowchart
```

Headless sanity check (CI-friendly, auto-answers every decision):

```
python -m examples.demos.branching_flowchart --smoke
```

## Things to try

1. **Press ▶ Run.** The active step glows blue. "Dispense droplet" has a
   40% simulated volume-check failure plus an operator check; each poses
   its prompt with routed buttons. The seeded AND shape fires when the
   answers are *Continue* + *Yes* — skipping the corrective mix straight
   to "Collect to waste". Otherwise the individual outcome routes apply
   (the *Retry* self-loop stops prompting after 3 tries).
2. **The ＋ plug under a step** opens the shape palette: one decision per
   contributing column (greyed once placed) and an AND operator. Placed
   decisions are shapes tethered to their step; delete or reconfigure
   them via right-click (Always prompt / Prompt first N times / Auto).
3. **Drag ports.** From a decision's colored outcome port to a step or
   group (route that answer), onto an AND shape (feed the combiner), or
   onto blank space — a "＋ New step" ghost appears and releasing mints a
   pre-routed step. The blue done-port routes step completion the same
   way. Edges snap to the node under the cursor (cyan glow) and wrap
   around boxes that sit in the way.
4. **"Operator inspect" has no placed shape** — it still prompts, using
   the provider defaults. Ticking *"Don't ask again this run"* in a
   prompt mints/updates the shape with the auto answer.
5. **Group / ungroup:** rubber-band a contiguous run of steps and press
   Group (or right-click blank canvas). Groups are jump targets too —
   routing to one enters its first step.
6. Rename (double-click), Arrange V/H, Fit, save/load the whole graph
   (tree + shapes + routes + positions) as JSON. Parameters are edited
   only in the table, which stays selection-synced with the canvas.

## How it maps onto the real app

| Demo | Real app |
|---|---|
| `columns.py` `ColumnModel`/`ColumnHandler`/`Column` | `pluggable_protocol_tree/interfaces/i_column.py` model/view/handler trio |
| `ColumnHandler.decision_specs()` + `ctx.request_decision()` | the proposed extension to `IColumnHandler` / `StepContext` |
| `model.py` `Row` tree, groups | `RowManager`'s `BaseRow`/`GroupRow` |
| `DecisionNode` / `OpNode` shapes | new per-protocol data, serialized like `protocol_metadata`'s `flow_view` layout in the xuhkrc branch |
| `executor.py` `DemoExecutor` | `pluggable_protocol_tree/execution/executor.py` — same worker thread, priority-bucket hook fan-out (parallel within a bucket, first exception sets `stop_event`), pause-at-step-boundaries, stop semantics, error>aborted>finished terminal precedence |
| `_resolve_routing` | the ONE structural change: `_run_steps` consults a routing resolver after `on_post_step` instead of `i += 1`. Steps without decisions fall through unchanged. |
| Qt signals on `ExecutorSignals` | Traits `Event`s observed with `dispatch="ui"` |
| `canvas.py` routing/ghost/groups | ported from `flow_graph_dialog.py` (xuhkrc branch) |
| Parameter table | the existing protocol tree (parameters only) |

### Semantics chosen (up for debate)

* All of a step's decisions resolve first (prompt or auto, in provider
  priority order). Routing then evaluates: **AND ops first** (all input
  outcomes chosen this round → the op's route wins), then the individual
  outcome routes (first non-"next" wins), then the step's completion
  route, then table order.
* An AND only combines outcomes from one step's decisions (enforced on
  drop); an op with no wired target is inert.
* "Auto after N" counts per (step, decision) per run; the auto answer is
  the provider's `default_outcome` unless the user picked one via "don't
  ask again".
* A jump re-enters the target step fresh; a group target means its first
  step. Completion self-loops are blocked (retries belong to decision
  outcomes); a decision outcome dragged back onto its own step is the
  retry loop.
* Route/wiring edits are allowed mid-run (read at resolve time);
  adding/deleting/regrouping steps mid-run is blocked.
