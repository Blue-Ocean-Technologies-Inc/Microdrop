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
   contributing column (greyed once placed) and the AND / OR operators.
   Placed decisions are shapes tethered to their step; delete or
   reconfigure them via right-click. Four prompt policies: *Always
   prompt*, **Auto first N times then prompt** (silent auto-retries
   before the user is forced to decide — the seeded Volume check
   auto-retries twice, then asks, and the prompt says so), *Prompt first
   N times then auto*, and *Auto (never prompt)*; the auto answer is
   picked when configuring. Right-click an operator to convert AND ⇄ OR.
3. **Drag ports.** From a decision's colored outcome port to a step or
   group (route that answer), onto an AND/OR shape (feed the combiner),
   onto **another decision of the same step** (a dashed *chain* edge:
   resolve serially — that decision is only asked when this outcome was
   chosen), or onto blank space — a "＋ New step" ghost appears and
   releasing mints a pre-routed step. The blue done-port routes step
   completion the same way. Edges snap to the node under the cursor
   (cyan glow) and wrap around boxes that sit in the way. The seeded
   protocol chains Volume check → Operator check on "Dispense droplet",
   so the operator is only consulted when the volume answer is
   *Continue*.
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

* Decisions with no incoming chain edge resolve together first, in
  provider-priority order. An outcome routed to a sibling decision shape
  is a **chain**: choosing it activates that decision, which resolves
  next (serial). A chained decision whose activating outcome wasn't
  chosen — or that never fired — is skipped that round.
* Routing then evaluates: **logic ops first** (AND = all input outcomes
  chosen this round, OR = any of them; creation order, first match
  wins), then the individual outcome routes in resolution order (first
  non-"next" wins), then the step's completion route, then table order.
* An op only combines outcomes from one step's decisions, and chains
  only link decisions of the same step (both enforced on drop); an op
  with no wired target is inert.
* Prompt policies count occurrences per (step, decision): "prompt first
  N then auto" suppresses the dialog after N asks; "auto first N then
  prompt" answers silently N times (auto-retry) and then escalates to
  the user. Counters reset when the step is departed, so each retry
  *streak* gets its own budget. The auto answer is the provider's
  `default_outcome` unless the user picked one (in the policy dialog or
  via "don't ask again").
* A jump re-enters the target step fresh; a group target means its first
  step. Completion self-loops are blocked (retries belong to decision
  outcomes); a decision outcome dragged back onto its own step is the
  retry loop.
* Route/wiring edits are allowed mid-run (read at resolve time);
  adding/deleting/regrouping steps mid-run is blocked.
