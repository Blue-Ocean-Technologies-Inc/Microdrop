# PPT-21: Protocol Quick-Actions Toolbar — Design

**Date:** 2026-05-28
**Branch:** `feat/433-ppt-21-protocol-quick-actions-toolbar`
**Issue:** [#433](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/433)

## Goal

Bring the legacy `protocol_grid/quick_action_bar.py` toolbar into the
pluggable protocol tree, but split it cleanly:

- **Architecture** (extension point, traits model, controller, toolbar
  widget) lives in `pluggable_protocol_tree` — the tree plugin ships
  with **zero** built-in actions, only the contribution surface.
- **All 8 legacy actions** are reborn as contributions from a new
  sibling plugin, `protocol_quick_action_tools` — full feature parity,
  no shared state with the tree plugin.

This mirrors how columns work today (`PROTOCOL_COLUMNS` extension
point, tree plugin owns the contract, other plugins contribute
columns) and keeps the tree plugin's responsibility focused.

## Background

Legacy `protocol_grid.quick_action_bar.QuickProtocolActions` is a
hard-coded `QWidget` with eight `QPushButton`s wired directly to
`PGCWidget` methods; `QuickProtocolActionsController` reacts to
selection and protocol-running state to enable/disable individual
buttons. It works, but it has no contribution mechanism — every
button is baked in, and the `(R)` keyboard shortcut for the report
browser is hand-wired on the widget.

The pluggable tree replaces `protocol_grid` over time. It already has
`ProtocolTreePane` (file ops `new_protocol` / `load_protocol_dialog` /
`save_protocol_dialog` exist; tree-structure ops live in the tree
widget's context menu), a `RowManager`, and an Envisage plugin with
an existing `PROTOCOL_COLUMNS` extension point pattern to follow.

### Existing building blocks (reused as-is)

- `ProtocolTreePane.new_protocol()`, `.load_protocol_dialog()`,
  `.save_protocol_dialog()` — file operations.
- `RowManager.add_step(parent_path, index, values=...)` — used by the
  context-menu insert handlers; reusable here.
- `protocol_state_tracker.PluggableProtocolStateTracker.is_modified`
  — informs `_confirm_proceed_or_abort` flows.
- `microdrop_style.button_styles.ICON_FONT_FAMILY` — material-symbols
  font already used by `_build_experiment_bar`.
- `pyface.qt.QtGui.QDesktopServices` + `QUrl.fromLocalFile` — opens
  HTML reports in the default browser.
- `protocol_grid/extra_ui_elements.py` `ReportBrowserDialog`
  (lines 942–1064) — self-contained `QDialog` we can port verbatim.

## Architecture

Three units; each has one clear job.

### 1. `pluggable_protocol_tree` — the contribution surface (no builtins)

```
pluggable_protocol_tree/
  interfaces/i_quick_action.py     ← NEW    IQuickAction interface
  models/quick_action.py           ← NEW    BaseQuickAction + QuickActionCtx
  views/quick_action_bar.py        ← NEW    QuickActionBar + QuickActionsController
  consts.py                        ← +      PROTOCOL_QUICK_ACTIONS extension-point id
  plugin.py                        ← +      extension point + plain list pass-through
  views/protocol_tree_pane.py      ← +      mount the bar; emit selection/running signals
```

**`IQuickAction` interface** (Traits — mirrors `IColumnHandler`):

```python
class IQuickAction(Interface):
    action_id  = Str            # stable id (e.g. "add_step"); used for logging/tests
    icon_text  = Str            # material-symbol name (e.g. "add", "delete")
    tooltip    = Str            # button tooltip
    priority   = Int(50)        # lower runs first; controls left-to-right order
    shortcut   = Str(default_value="")   # QKeySequence string ("R", "Ctrl+S"); "" = none

    def on_execute_action(self, ctx): ...
    def is_enabled(self, ctx) -> bool: return True
```

**`QuickActionCtx`** (small `HasStrictTraits` value object built fresh
on each invocation):

```python
class QuickActionCtx(HasStrictTraits):
    pane           = Instance("ProtocolTreePane")   # access to .manager, .widget.tree,
                                                    # .executor, .application, .experiment_manager
    selected_paths = Tuple()                        # tuple of dotted-path tuples currently selected
    is_running     = Bool(False)                    # protocol_state_tracker / executor running
```

**Extension point** — a clone of the `PROTOCOL_COLUMNS` pattern in
`plugin.py`:

```python
_quick_action_extension_point = ExtensionPoint(
    List(Instance(IQuickAction)), id=PROTOCOL_QUICK_ACTIONS,
    desc="Quick-action buttons contributed by other plugins.",
)
contributed_quick_actions = List(desc="...")     # plain List for tests
```

`PluggableProtocolTreePlugin.start()` populates
`contributed_quick_actions` from the extension point and passes the
list into `PluggableProtocolDockPane` the same way it passes columns
in. `_assemble_quick_actions()` sorts contributions by
`(priority, action_id)` so ordering is deterministic.

**Tree-plugin builtins:** none. The plugin ships an empty default for
`contributed_quick_actions`. This is the architectural commitment to
the split.

### 2. `QuickActionBar` + `QuickActionsController` (view layer)

`QuickActionBar(QWidget)` — a horizontal row of icon-only
`QToolButton`s using `ICON_FONT_FAMILY`. Pure rendering: takes the
sorted list of actions, builds one button per action, exposes
`buttons: Dict[str, QToolButton]` keyed by `action_id`. No state.

`QuickActionsController` — wires the bar to the pane:

- Builds a fresh `QuickActionCtx` each time a button fires or
  `is_enabled` needs re-checking.
- Connects to two new pane-level signals (see §4):
  `pane.selection_changed`, `pane.protocol_running_changed`.
- On every signal: walks the action list, sets
  `button.setEnabled(action.is_enabled(ctx))`. When `is_running` is
  `True`, the whole bar is disabled — the per-action `is_enabled`
  check is short-circuited so a contribution can't accidentally
  light up during a run.
- On button click: `_execute(action)` → `try: action.on_execute_action(ctx)
  except Exception: logger.error(...)`. A buggy contribution can't
  crash the GUI.

**Shortcut wiring** (the new trait):

After the bar is built, the controller registers one `QShortcut` per
action whose `shortcut` is non-empty:

```python
qs = QShortcut(QKeySequence(action.shortcut), pane)
qs.setContext(Qt.WidgetWithChildrenShortcut)
qs.activated.connect(lambda a=action: self._execute(a))
```

- `WidgetWithChildrenShortcut` scopes the binding to the pane (and its
  descendants) — prevents an action's key from colliding with the
  same key elsewhere in the app (DV camera, etc.).
- Shortcuts route through `_execute`, so they respect
  `is_enabled(ctx)` and `is_running` exactly like a button click —
  pressing **R** during a run is a no-op.
- Conflict detection: track shortcut strings as we wire; if two
  contributions claim the same key, log a warning naming both
  `action_id`s and skip the second registration. Prevents silent
  loss-of-binding bugs when plugins overlap.

### 3. Pane integration

`ProtocolTreePane`:

- New attribute `self.quick_action_bar` built in `__init__` from the
  injected contributions (constructor gains
  `quick_actions: List[IQuickAction] = None`, same shape as the existing
  `columns_or_manager`/`columns` flow).
- Mounted **below** the tree in `_build_layout`:
  `layout.addWidget(self.widget); layout.addWidget(self.quick_action_bar)`.
  Mirrors legacy placement.
- New Qt signals (the controller's data feed):
  - `protocol_running_changed = Signal(bool)` — emitted with `True` in
    `_on_protocol_started`, `False` in `_on_protocol_terminated`.
  - `selection_changed = Signal()` — connected to the tree's existing
    `selectionModel().selectionChanged` (parameterless re-emit; the
    controller queries the model directly for paths).

`PluggableProtocolDockPane._make_dock_pane` (and the demo window
factory) pass `quick_actions=self._assemble_quick_actions()` into the
pane.

### 4. Pane helpers used by contributions

Contributed actions stay Qt-free where they can; pane helpers absorb
the Qt dialog work. Five small helpers added to `ProtocolTreePane`:

- `add_step_after_selection()` — current path + 1 under same parent,
  or append at root when nothing is selected.
- `add_group_after_selection()` — same logic, creates a `GroupRow`.
- `delete_selected_rows()` — collect paths from
  `tree.selectionModel().selectedRows()`, sort tail-first so removals
  don't shift indices, call `manager.remove_row(path)`.
- `import_into_selected_group()` — `QFileDialog.getOpenFileName` →
  load JSON → merge top-level rows under the selected group's path
  via `manager.add_step` / `add_group`. No-op if selection is not a
  single `GroupRow`.
- `browse_reports_dialog()` — glob
  `<experiment_dir>/reports/*.html`, open the ported
  `ReportBrowserDialog(report_paths, parent=self).exec()`.

Existing pane methods reused unchanged: `new_protocol()`,
`load_protocol_dialog()`, `save_protocol_dialog()`.

## The new `protocol_quick_action_tools` plugin

A sibling under `src/` mirroring the layout of
`peripheral_protocol_controls` / `dropbot_protocol_controls`.

```
protocol_quick_action_tools/
  __init__.py
  plugin.py               # ProtocolQuickActionToolsPlugin
  consts.py               # PKG, PKG_name, action-id constants
  quick_actions/
    __init__.py
    base.py               # _PaneBackedAction + small predicates
                          #   (is_single_group_selected, has_selection, ...)
    add_step.py           # make_add_step_action()
    add_group.py          # make_add_group_action()
    delete_row.py         # make_delete_row_action()
    import_protocol.py    # make_import_protocol_action()
    open_protocol.py      # make_open_protocol_action()
    save_protocol.py      # make_save_protocol_action()
    new_protocol.py       # make_new_protocol_action()
    browse_reports.py     # make_browse_reports_action()
  views/
    __init__.py
    report_browser_dialog.py     # ported from protocol_grid/extra_ui_elements.py:942-1064
                                  # ReportBrowserDialog + _ReportSortableTreeWidgetItem
  tests/
    test_quick_actions.py        # one test per action: execute + is_enabled matrix
```

**`plugin.py` shape:**

```python
class ProtocolQuickActionToolsPlugin(Plugin):
    id = f"{PKG}.plugin"
    name = PKG_name

    contributed_quick_actions = List(contributes_to=PROTOCOL_QUICK_ACTIONS)

    def _contributed_quick_actions_default(self):
        return [
            make_add_step_action(),
            make_delete_row_action(),
            make_add_group_action(),
            make_import_protocol_action(),
            make_open_protocol_action(),
            make_save_protocol_action(),
            make_new_protocol_action(),
            make_browse_reports_action(),
        ]
```

**Live-app wiring:** add `ProtocolQuickActionToolsPlugin` to
`examples/plugin_consts.py` next to the existing frontend plugins so
it loads with the dock pane. The pane itself doesn't reference this
plugin — it just reads the extension point.

## The eight actions

Legacy left-to-right order preserved via `priority`:
`add_step=10`, `delete_row=20`, `add_group=30`, `import_protocol=40`,
`open_protocol=50`, `save_protocol=60`, `new_protocol=70`,
`browse_reports=80`.

| # | id | icon | tooltip | Executes | Enabled when | Shortcut |
|---|---|---|---|---|---|---|
| 1 | `add_step` | `add` | "Add step below selection" | `ctx.pane.add_step_after_selection()` | not running | — |
| 2 | `delete_row` | `delete` | "Delete selected step / group" | `ctx.pane.delete_selected_rows()` | not running AND `len(selected_paths) >= 1` | — |
| 3 | `add_group` | `playlist_add` | "Add group" | `ctx.pane.add_group_after_selection()` | not running | — |
| 4 | `import_protocol` | `unarchive` | "Import protocol into selected group" | `ctx.pane.import_into_selected_group()` | not running AND `len(selected_paths) == 1` AND target row is a `GroupRow` | — |
| 5 | `open_protocol` | `file_open` | "Open Protocol" | `ctx.pane.load_protocol_dialog()` | not running | — |
| 6 | `save_protocol` | `save` | "Save Protocol" | `ctx.pane.save_protocol_dialog()` | not running | — |
| 7 | `new_protocol` | `new_window` | "New protocol" | `ctx.pane.new_protocol()` | not running | — |
| 8 | `browse_reports` | `summarize` | "Browse session reports (R)" | open ported `ReportBrowserDialog` over globbed `<experiment_dir>/reports/*.html` | not running AND `experiment_manager is not None` | `R` |

Only `browse_reports` ships with a shortcut in this PR. Once the
trait is in place, adding `Ctrl+N` / `Ctrl+O` / `Ctrl+S` to others is
a one-line factory change in a follow-up.

## Report browser

Port `protocol_grid/extra_ui_elements.py` lines 942–1064 verbatim
into `protocol_quick_action_tools/views/report_browser_dialog.py`:

- `_ReportSortableTreeWidgetItem` — numeric Size / chronological Date
  sort (override `__lt__`).
- `ReportBrowserDialog(report_paths: List[str], parent=None)` — search
  bar, sortable `Name`/`Size`/`Date Created` columns, double-click /
  Open button → `QDesktopServices.openUrl(QUrl.fromLocalFile(path))`.

The dialog is fully decoupled from `protocol_grid` already — its only
input is a list of path strings. We feed it whatever the
`browse_reports` action provides.

**Where reports come from:** glob `<experiment_dir>/reports/*.html`
at click time. This is a deliberate improvement over the legacy,
which only showed reports from the current session (tracked in
`ProtocolDataLogger.all_report_paths`). Globbing the directory
surfaces historical reports too and keeps the logging controller
stateless — no `all_report_paths` accumulator threaded through
`ProtocolLoggingController`.

## Data flow

```
user clicks button / presses shortcut
  -> QuickActionsController._execute(action)
       -> ctx = QuickActionCtx(pane, selected_paths, is_running)
       -> action.on_execute_action(ctx)
            -> ctx.pane.<helper>()  (or directly manipulates ctx.pane.manager)

selection changes  -> pane.selection_changed
  -> controller._refresh_enabled()
       -> for action in actions:
            button.setEnabled(action.is_enabled(ctx) and not ctx.is_running)

protocol starts  -> pane.protocol_running_changed.emit(True)
  -> controller._refresh_enabled() (whole bar disabled)
protocol ends    -> pane.protocol_running_changed.emit(False)
  -> controller._refresh_enabled() (back to per-action gating)
```

## Error handling

- **Buggy contribution:** `_execute` wraps `on_execute_action` and
  `is_enabled` in `try/except` that logs at `error` / `warning`
  respectively. A misbehaving plugin disables only its own button —
  it can't break the rest of the bar or crash the pane.
- **Missing experiment manager:** every action that needs one
  (`browse_reports`, `import_into_selected_group` if you wanted to
  scope to a default dir later) gates its `is_enabled` on
  `ctx.pane.experiment_manager is not None`. Demos that pass `None`
  see those buttons stay greyed out — same graceful-degradation rule
  as the existing experiment-bar buttons.
- **Shortcut conflicts:** log a warning naming both `action_id`s,
  skip the second registration. The first contribution wins
  deterministically (priority-sorted order).
- **Unreadable / missing reports dir:** `glob` returns an empty list;
  `ReportBrowserDialog([], parent=self).exec()` still opens with an
  empty table and the search box. Users see "no reports yet" rather
  than a crash.

## Testing

**`pluggable_protocol_tree/tests/`**

- `test_quick_action_bar.py` — the bar widget renders one button per
  action in `(priority, action_id)` order, button text equals
  `icon_text`, tooltip equals `tooltip`, `is_enabled=False` actions
  start disabled.
- `test_quick_actions_controller.py` — fake action with `is_enabled`
  toggle:
  - selection_changed fires → `_refresh_enabled` re-queries
    `is_enabled`.
  - protocol_running_changed(True) → all buttons disabled regardless
    of `is_enabled`.
  - protocol_running_changed(False) → buttons re-query `is_enabled`.
  - click on enabled button → `on_execute_action` called once with
    correct `ctx`.
  - click on disabled button → `on_execute_action` NOT called.
  - exception in `on_execute_action` → logged, other buttons stay
    responsive.
- `test_quick_actions_shortcuts.py`:
  - action with `shortcut="R"` registers a widget-scoped `QShortcut`
    on the pane.
  - two actions claiming the same shortcut → second registration is
    skipped + warning logged.
  - pressing the shortcut while `is_running=True` → action is NOT
    executed.
- `test_protocol_tree_pane.py` (extend):
  - `add_step_after_selection` inserts a step at the right path under
    various selection states (root, child, nothing).
  - `delete_selected_rows` removes tail-first.
  - `import_into_selected_group` no-ops when selection is not a
    single `GroupRow`.
  - `browse_reports_dialog` globs the reports dir and constructs the
    dialog with the right paths (dialog `exec` monkeypatched).

**`protocol_quick_action_tools/tests/`**

- `test_quick_actions.py` — one block per action. Build a
  `QuickActionCtx(pane=MagicMock(), selected_paths=..., is_running=...)`
  and assert:
  - `on_execute_action(ctx)` calls the right pane method (or
    constructs the right dialog).
  - `is_enabled(ctx)` matrix is correct for `(is_running × selection
    shape)` — at minimum: running=True, empty selection, single step,
    single group, multi-row.

No Envisage / Redis dependencies in either test file — both run in
the headless test environment.

## Out of scope

- **No `all_report_paths` accumulator** in
  `ProtocolLoggingController`. Globbing the dir is the source of
  truth.
- **No persistence** of bar layout or hidden-action preferences. The
  bar reflects the current contribution set every session.
- **No file-menu refactor.** File operations live on the bar *and* in
  the existing File menu — both call the same pane methods, so they
  stay in sync without further plumbing.
- **No additional keyboard shortcuts** beyond `R`. Adding more is a
  one-line trait change per action in a follow-up PR.
- **No material-symbols font loading.** Reuses the existing
  `ICON_FONT_FAMILY` infrastructure already loaded by the dock-pane
  init path.
- **No theme reactivity beyond what `QToolButton` already does.** The
  legacy bar restyled itself on palette change; the new bar inherits
  the pane's stylesheet and re-renders icons on theme switch via the
  font family alone.
