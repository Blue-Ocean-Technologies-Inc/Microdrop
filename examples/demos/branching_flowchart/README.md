# Branching protocol flowchart — standalone UX demo

A self-contained prototype for testing one idea: **the protocol's flow is
drawn graphically on a node canvas, while the table only sets step
parameters.** Column providers contribute *Decision* objects (a question +
possible answers with default routes); at run time a decision fires a
prompt dialog, and the clicked answer sends execution down the edge the
user drew — or the provider's default if they drew nothing.

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

1. **Press ▶ Run.** Steps light up blue as they execute. "Dispense
   droplet" has a 50% simulated volume-check failure — when it fails you
   get the prompt with **Retry / Continue / Abort** buttons, each showing
   where it will route. The seeded protocol has *Retry* drawn as an orange
   self-loop and is configured "auto after 3", so after 3 prompts it stops
   asking and silently takes the default.
2. **"Operator inspect"** always prompts (its *Operator check* cell is
   ticked). *No* is pre-wired back to "Dispense droplet" — a cross-edge
   drawn on the canvas.
3. **Reroute while looking at it:** drag from any colored outcome port (or
   the dark ▸ done-port) and drop on another step. Delete a selected edge
   to fall back to the provider default / table order.
4. **Right-click a node** → per-decision "Always prompt / Prompt first N
   times / Auto". Or tick *"Don't ask again this run"* inside the prompt
   itself.
5. **Edit the table** — values repaint on the nodes immediately; set *Fail
   chance* to 0 and the Volume-check strip greys out (decision dormant).
6. Add/rename/delete steps, auto-layout, save/load the whole graph as
   JSON (routes + positions included).

## How it maps onto the real app

| Demo | Real app |
|---|---|
| `columns.py` `ColumnModel`/`ColumnHandler`/`Column` | `pluggable_protocol_tree/interfaces/i_column.py` model/view/handler trio |
| `ColumnHandler.decision_specs()` + `ctx.request_decision()` | the proposed extension to `IColumnHandler` / `StepContext` |
| `executor.py` `DemoExecutor` | `pluggable_protocol_tree/execution/executor.py` — same worker thread, priority-bucket hook fan-out (parallel within a bucket, first exception sets `stop_event`), pause-at-step-boundaries, stop semantics, terminal-signal precedence |
| `_resolve_routing` / `_verdict_for` | the ONE structural change: `_run_steps` consults a route resolver instead of `i += 1`. Steps without decisions fall through unchanged. |
| Qt signals on `ExecutorSignals` | Traits `Event`s observed with `dispatch="ui"` |
| `canvas.py` Graphics View scene/view | same idioms as `device_viewer`'s `electrode_scene.py` / `video_canvas.py` |
| Parameter table | the existing protocol tree (parameters only) |

Route data is tiny and serializes with the protocol: per step a
`next_target` (completion route) plus `{decision_id: {routes, mode,
auto_after, auto_outcome}}`. Targets are step ids or the sentinels
next / self / end / abort.

### Semantics chosen (up for debate)

* Decisions resolve after `on_post_step`, in provider-priority order; the
  first outcome that routes anywhere other than "next" wins and later
  decisions from the same step are skipped (logged).
* "Auto after N" counts per (step, decision) per run; the auto answer is
  the provider's `default_outcome` unless the user picked one via "don't
  ask again".
* A jump re-enters the target step fresh. Completion self-loops are
  blocked (retries belong to decision outcomes); decision self-loops are
  the retry mechanism.
* Route edits and table edits are allowed mid-run (read at resolve time);
  adding/deleting steps mid-run is blocked.
