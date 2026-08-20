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

0. **Editing is safe:** every change — routes, shapes, groups, deletes,
   moves, table edits — is undoable (Ctrl+Z / Ctrl+Shift+Z, or the
   toolbar ↶ ↷). A collapsible legend (bottom-right) keys the visual
   vocabulary.
1. **Press ▶ Run.** The active step glows blue, and the seed exercises
   every construct:
   * *Serial chain* — on "Dispense droplet", the volume check
     auto-retries twice, then asks; answering **Continue** activates the
     chained operator confirm (the dashed "Continue → then" edge). The
     operator is never asked unless the volume check escalated first.
   * *AND* — volume **Continue** + operator **Yes** ("manually
     verified") fires the violet AND: skip the droplet-detect sensor
     step and formally enter the "Mix cycle" group (its ×2 passes
     apply).
   * *Group restart* — "Droplet detect" fails 35% of the time; its
     **Restart** is wired to the "Dispense & verify" group frame, so the
     whole group re-enters formally.
   * *OR* — "Operator inspect" poses two independent checks in the same
     round (contrast with the chained pair); if EITHER the operator says
     **No** OR the sensor sees no droplet (**Redo prep** — a custom
     button label), the teal OR sends the run back to redo the whole
     "Dispense & verify" group.
2. **The ＋ plug under a step** opens the shape palette: one decision per
   contributing column (greyed once placed) and the AND / OR operators.
   Placed decisions are shapes tethered to their step; delete or
   reconfigure them via right-click. Four prompt policies: *Always
   prompt*, **Auto first N times then prompt** (silent auto-retries
   before the user is forced to decide — the seeded Volume check
   auto-retries twice, then asks, and the prompt says so), *Prompt first
   N times then auto*, and *Auto (never prompt)*; the auto answer is
   picked when configuring. Right-click an operator to convert AND ⇄ OR.
   Operator shapes are self-describing cards that summarize their
   operation in text — `Volume check: Continue  &  Operator check: Yes
   → group 'Mix cycle'` — each input line colored by its outcome, with
   the priority in the header and a ⚠ note while unwired.
   Prompts open **next to the deciding shape** with its edges highlighted
   — the buttons and the drawn edges are the same choices. Keys 1..n
   answer; Esc takes the provider default; the toolbar's **Unattended**
   timer auto-answers after N seconds so an unwatched run never stalls.
3. **Drag ports.** From a decision's colored outcome port to a step or
   group (route that answer), onto an AND/OR shape (feed the combiner),
   onto **another decision of the same step** (a dashed *chain* edge:
   resolve serially — that decision is only asked when this outcome was
   chosen), or onto blank space — a "＋ New step" ghost appears and
   releasing mints a pre-routed step. The blue done-port routes step
   completion the same way. Edges snap to the node under the cursor
   (cyan glow) and wrap around boxes that sit in the way.
4. **"Operator inspect" has no placed shape** — it still prompts, using
   the provider defaults. Ticking *"Don't ask again this run"* in a
   prompt mints/updates the shape with the auto answer.
4b. **Watch the run on the canvas, not just the log.** The edge the
   executor follows flashes bright and the last few stay warm (a
   decaying trail); the active step glows blue with the previous ones
   faintly marked; **◎ Follow** keeps the running step centered. Silent
   auto-answers and group repeat passes pop a toast next to the
   responsible shape.
5. **Groups render as frames** — a container outline around their
   members. Drag the title bar to move the whole subtree; click ▾ to
   collapse a group to a chip (edges into its interior re-aim at the
   chip; wholly-internal edges hide). **Groups are real, not just
   visual.** The seed has two: "Dispense &
   verify" (Dispense + Droplet detect) and "Mix cycle ×2" (right-click a
   group → *Repetitions…*). A **formal group entry** — sequential
   fall-through, or a route drawn to the **group node** — fires the
   providers' `on_group_enter` hooks (watch the "Pre-charging
   electrodes…" log line) and schedules the group's repeat passes; the
   run log narrates every enter / repeat-pass / leave. A route drawn to
   a **step inside the group** is an informal jump: no entry hooks, no
   repeat restart — the log says so when it happens. The seeded
   droplet-detect scenario shows why the distinction matters: Droplet
   detect is the *last* step of its group, and its *Restart* outcome is
   routed to the group frame, so a missing droplet formally re-enters the
   whole group (hooks + fresh pass budget). Drag that edge onto
   "Dispense droplet" instead to feel the other behavior.
5b. **Terminal nodes and default glyphs.** ⏹ Stop and ▦ Finish are
   always on the canvas: drop any port on them to route abort/finish
   explicitly (drawn as real edges). Outcomes still on their provider
   default show a glyph after the label (↻ retry · → next · ⏹ abort ·
   ▦ finish) so unrouted behaviour is visible without hovering.
6. **Group / ungroup:** rubber-band a contiguous run of steps and press
   Group (or right-click blank canvas).
7. **The parameter grid is the protocol TREE**, not a flat list: groups
   are parent rows (bold, with dotted numbering — 2.1, 2.2 …) and the
   **Reps** column is editable on both groups (passes per formal entry)
   and steps (in-place repeats on fall-through; ×N shows on the slab).
   Collapsing a group row in the grid collapses its frame on the canvas
   and vice versa; the running step's row is highlighted live.
8. **Custom button labels:** right-click an outcome edge (or a decision
   shape → *Button labels*) to rename an answer — the prompt button, the
   edge label, and the port all use it (e.g. rename *Retry* to
   *Re-dispense*).
9. Rename (double-click), duplicate steps with their shapes (Ctrl+D),
   double-click blank canvas to add a step there, hover a node to light
   up its connected edges, unwired AND/OR shapes call themselves out,
   Arrange V/H, Fit, 📷 export the chart as PNG, and save/load the whole
   graph (tree + shapes + routes + positions) as JSON. The grid stays
   selection-synced with the canvas.

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
* Routing then arbitrates all matched candidates by **per-edge
  priority** (lower wins): matched AND/OR ops (all/any input outcomes
  chosen this round) default to p10, outcome edges to p20 — so ops beat
  edges unless an edge is raised above them (edge context menu →
  *Priority…*; non-default priorities show as `[pN]` on the edge). Ties
  keep op-creation order, then resolution order. If nothing matched:
  the step's completion route, then table order. The run log narrates
  each arbitration ("X (p5) beat Y (p10)").
* The **auto answer** — used by auto policies, "don't ask again", and
  the Unattended timer — is visible and settable on the flowchart:
  the ringed outcome port is the current auto pick; double-click a port
  to make it the auto answer (double-click the ringed one to reset to
  the provider default). Decision badges show it, e.g.
  `[auto Retry ×2 → ask]`.
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
* A jump re-enters the target step fresh. Completion self-loops are
  blocked (retries belong to decision outcomes); a decision outcome
  dragged back onto its own step is the retry loop.
* **Group targets differ from first-step targets.** Routing to a group
  node is a formal entry: `on_group_enter`/`on_group_exit` hooks fire
  and the group's `repetitions` budget (re)starts — including when the
  route comes from inside the group (restart). Routing to a step inside
  the group jumps into the sequence with no hooks and no repeat
  restart. Sequential fall-through into a group counts as formal;
  fall-through past a group's last step replays the group while passes
  remain (innermost group first); explicit drawn routes override
  remaining repeats.
* Route/wiring edits are allowed mid-run (read at resolve time);
  adding/deleting/regrouping steps mid-run is blocked.
