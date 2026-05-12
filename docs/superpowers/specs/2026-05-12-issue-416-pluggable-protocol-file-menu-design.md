# PPT-10.3 Design — Wire `&Protocol` file menu + dirty-state title for the pluggable protocol tree

**Date:** 2026-05-12
**Status:** Draft, pre-implementation
**Issue:** [#416 — PPT-10.3 wire protocol file menu (New / Load / Save / Save As) and dirty-state title for the pluggable protocol tree](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/416)
**Parent:** [#361 — Pluggable Protocol Tree umbrella]
**Predecessors:** PPT-10.1 ([#411]) — `ProtocolTreePane` extraction + `save_to_dialog`/`load_from_dialog`. PPT-10.2 ([#414]) — device-viewer sync.
**Blocker for:** PPT-9 ([#371]) — legacy `protocol_grid` deletion (this brings the new pane to feature parity).

## 0. Scope

The persistence APIs already exist: `RowManager.to_json` / `from_json` / `set_state_from_json` (PPT-1), and `ProtocolTreePane.save_to_dialog` / `load_from_dialog` (PPT-10.1). What's missing is the menu wiring + dirty-state bookkeeping + title display + warn-on-unsaved that the legacy `protocol_grid` plugin provides.

This spec covers:
- A `&Protocol` top-level menu with `&Create New`, `&Load`, `&Save`, `Save &as`.
- A `PluggableProtocolStateTracker` HasTraits service that tracks `protocol_name`, `loaded_protocol_path`, `is_modified` and rewrites the dock-pane title.
- Pane methods that wrap save/load/new with the unsaved-changes confirm dialog.
- An `application_exiting` observer that vetoes app exit on unsaved changes if the user picks NO.

**Out of scope:**
- Auto-save / crash-recovery — separate spec if desired.
- Changes to the legacy `protocol_grid` plugin — slated for deletion in PPT-9.
- Persistence format / schema migration — PPT-1's JSON contract is the source of truth.
- Sticky-notes / experiment-bar wiring — already in PPT-10.1.

## 1. Decisions locked in during brainstorming

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Where does "dirty" come from? | Observe `RowManager.rows_changed` event | It already fires on every mutation path (add_step, add_group, remove, move, paste, set_value(s), apply, set_state_from_json). Single observer. No per-callsite `_mark_modified` plumbing like legacy widget.py. |
| 2 | How to avoid marking dirty during load/new? | Post-event reset: helper explicitly sets `is_modified = False` after `set_state_from_json`/root-reset returns | `set_state_from_json` fires `rows_changed`, which would flip the tracker dirty. Trait observers are synchronous — by the time the helper returns, the flip has already happened. Resetting after the fact is clean and avoids a `_loading_from_file` boolean. |
| 3 | Tracker owns dock_pane reference? | Yes — direct rewrite of `dock_pane.name` from observer | Matches legacy `ProtocolStateTracker`. Tracker accepts `dock_pane=None` so unit tests can construct it headlessly. The pane wires the reference when mounting. |
| 4 | Menu location | Top-level `&Protocol` in MenuBar | Issue wording: "the `&Protocol` menu in the main menubar." Legacy buries it under File / before-Exit, which is awkward. Top-level matches the issue and is cleaner. (If the user prefers File-submenu placement we can flip the SchemaAddition `path` in one line.) |
| 5 | Guard decorator vs inline check | Inline `_confirm_proceed_or_abort()` helper called at the top of `new_protocol` / `load_protocol_dialog` | Legacy `@ensure_protocol_saved` decorator coupled the dirty check to method signatures. Pane methods are short enough that a 2-line inline call is clearer than reaching through `self` for the tracker inside a closure-style decorator. Save / Save-As skip the guard (they don't risk losing data). |
| 6 | App-exit guard | Observe `application_exiting` Vetoable event; on dirty + NO, set `event.veto = True` | New behavior beyond legacy (legacy only saves column settings on exit). Veto is the right primitive — keeps the app open so the user can save. |
| 7 | "New protocol" reset mechanism | Direct `manager.root = GroupRow(name="Root")` + `protocol_metadata = {}` + `selection = []` + fire `rows_changed` | Simpler than round-tripping an empty payload through `set_state_from_json`. RowManager already exposes the necessary traits. |
| 8 | Where the tracker lives | On `ProtocolTreePane` (`self.protocol_state_tracker`) | Both demo and dock-pane mount the same `ProtocolTreePane`. Putting the tracker on the pane means both contexts get the dirty/title behavior for free — though only the dock-pane path has a `DockPane.name` to rewrite (demo uses a `QMainWindow.setWindowTitle` if we ever wire it; out of scope here). |
| 9 | DockPaneAction wiring (4 methods on dock pane) | Add `new_protocol` / `load_protocol_dialog` / `save_protocol_dialog` / `save_as_protocol_dialog` to `PluggableProtocolDockPane`, each delegating to `self.control.widget()` (the `ProtocolTreePane`) | Matches legacy `PGCDockPane` exactly. The `control.widget()` accessor is how Pyface dock panes expose their hosted widget to `DockPaneAction(method=...)`. |
| 10 | Where the actual save/load implementation lives | Stays on `ProtocolTreePane` (extends existing `save_to_dialog` / `load_from_dialog`) | Existing methods become the inner half; new wrapper methods (`save_protocol_dialog`, etc.) layer dirty bookkeeping + guard prompts on top. Keeps the file-IO and the bookkeeping in the same class. |

## 2. File layout

```
microdrop-py/src/pluggable_protocol_tree/
├── menus.py                                            # NEW — 4 DockPaneAction factories + protocol_menu_factory()
├── services/
│   └── protocol_state_tracker.py                       # NEW — PluggableProtocolStateTracker(HasTraits)
├── views/
│   ├── protocol_tree_pane.py                           # MODIFIED — own tracker; wrap save/load/new; exit-guard observer; mutation observer
│   └── dock_pane.py                                    # MODIFIED — add 4 delegate methods + wire tracker to self.name
├── plugin.py                                           # MODIFIED — contribute protocol_menu_factory via SchemaAddition
└── tests/
    ├── test_protocol_state_tracker.py                  # NEW — pure HasTraits unit tests
    ├── test_menus.py                                   # NEW — factory shape, ids/methods
    └── test_protocol_tree_pane_file_menu.py            # NEW — qapp-level integration

docs/superpowers/specs/
└── 2026-05-12-issue-416-pluggable-protocol-file-menu-design.md   # this file
```

## 3. Architecture

### 3.1 `PluggableProtocolStateTracker(HasTraits)`

```
protocol_name           : Str("untitled")
loaded_protocol_path    : File("")
is_modified             : Bool(False)
modified_tag            : Str(" [modified]")
dock_pane               : Instance(DockPane, None)   # optional — None in tests
pkg_display_name        : Str(PKG_name)              # "Pluggable Protocol Tree"

display_name()                                       # returns the formatted dock-pane title
update_display_name()                                # rewrites self.dock_pane.name when set
@observe("protocol_name, is_modified")               # triggers update_display_name
set_loaded(path: str)                                # path/name/is_modified=False
set_saved(path: str)                                 # path/name/is_modified=False
reset()                                              # untitled, "", is_modified=False
mark_modified()                                      # is_modified = True
```

Title format: `"<PKG_name> - <protocol_name><modified_tag if dirty>"`, e.g., `"Pluggable Protocol Tree - my_assay [modified]"`.

### 3.2 Integration on `ProtocolTreePane`

```
self.protocol_state_tracker = PluggableProtocolStateTracker()
self.manager.observe(self._on_manager_rows_changed, "rows_changed")

# new methods (called by dock-pane delegates):
def save_protocol_dialog(self): ...      # save to known path, else delegate to save_as
def save_as_protocol_dialog(self): ...   # extends save_to_dialog -> set_saved on success
def load_protocol_dialog(self): ...      # guard -> extends load_from_dialog -> set_loaded on success
def new_protocol(self): ...              # guard -> reset manager + reset tracker

# helpers:
def _confirm_proceed_or_abort(self) -> bool: ...
def _on_manager_rows_changed(self, event): ...   # is_modified = True
def _on_application_exiting(self, event): ...    # vetoes on dirty + NO
```

The `_on_manager_rows_changed` observer is unconditional — it always sets `is_modified = True`. `set_loaded` / `set_saved` / `reset` (called *after* the manager mutation completes) override the flag back to False.

The `application_exiting` observer is attached only when `self.application is not None` and detached in `closeEvent`.

### 3.3 Dock-pane delegates + name binding

```python
class PluggableProtocolDockPane(TraitsDockPane):
    ...
    def new_protocol(self):              self.control.widget().new_protocol()
    def load_protocol_dialog(self):      self.control.widget().load_protocol_dialog()
    def save_protocol_dialog(self):      self.control.widget().save_protocol_dialog()
    def save_as_protocol_dialog(self):   self.control.widget().save_as_protocol_dialog()
```

In `create_contents`, after constructing `ProtocolTreePane`, set `pane.protocol_state_tracker.dock_pane = self` so the title-rewrite observer has a target.

### 3.4 Menu + plugin contribution

```python
# menus.py
def new_protocol_factory():     DockPaneAction(..., method="new_protocol",          name="&Create New")
def load_dialog_factory():      DockPaneAction(..., method="load_protocol_dialog",  name="&Load")
def save_dialog_factory():      DockPaneAction(..., method="save_protocol_dialog",  name="&Save")
def save_as_dialog_factory():   DockPaneAction(..., method="save_as_protocol_dialog", name="Save &as")

def protocol_menu_factory():
    return SMenu(
        new_protocol_factory(),
        load_dialog_factory(),
        save_dialog_factory(),
        save_as_dialog_factory(),
        id="pluggable_protocol_tree.tools_menu",
        name="&Protocol",
    )
```

```python
# plugin.py — _contributed_task_extensions_default
TaskExtension(
    task_id=self.task_id_to_contribute_view,
    dock_pane_factories=[self._make_dock_pane],
    actions=[
        SchemaAddition(
            factory=protocol_menu_factory,
            path="MenuBar",
            after="File",
        ),
    ],
)
```

`path="MenuBar"` + `after="File"` slots the menu in the top menubar right after `&File` (matches the issue's "main menubar" phrasing).

## 4. Behaviors / acceptance criteria mapping

| Issue checkbox | Where it's satisfied |
|---|---|
| `menus.py exports protocol_menu_factory()` | §3.4 |
| `PluggableProtocolDockPane` has 4 methods | §3.3 |
| `PluggableProtocolStateTracker(HasTraits)` with named traits | §3.1 |
| DockPane name updates: untitled → name → name [modified] | tracker observer in §3.1 |
| Save → write JSON to loaded path or fall back to Save As; clear dirty | `save_protocol_dialog` in §3.2 |
| Save As → dialog → JSON → set path/name/clean | `save_as_protocol_dialog` in §3.2 |
| Load → guard → dialog → set_state_from_json → set path/name/clean | `load_protocol_dialog` in §3.2 |
| New → guard → reset manager + tracker | `new_protocol` in §3.2 |
| App-exit guard prompts on unsaved | `_on_application_exiting` in §3.2 |
| Tests (six listed scenarios) | §5 |
| Manual smoke (run_device_viewer_pluggable.py) | §6 |

## 5. Test plan

### 5.1 `test_protocol_state_tracker.py` (no Qt, no DockPane required)
- `test_default_state` — `protocol_name == "untitled"`, `is_modified is False`, `loaded_protocol_path == ""`.
- `test_set_loaded_sets_name_path_clears_dirty`
- `test_set_saved_sets_name_path_clears_dirty`
- `test_reset_returns_to_defaults`
- `test_display_name_format_clean_dirty_and_untitled`
- `test_dock_pane_name_rewritten_on_change` — pass a stub object exposing a writable `name` attribute; observe both `protocol_name` and `is_modified` changes.

### 5.2 `test_menus.py` (no Qt)
- `test_factory_returns_smenu_with_four_actions`
- `test_action_ids_and_methods_match_expected` — verifies each DockPaneAction's `method=` and `dock_pane_id=`.

### 5.3 `test_protocol_tree_pane_file_menu.py` (uses `qapp` fixture)
- `test_mutation_marks_dirty` — add a step → tracker.is_modified True, dock-pane name has `[modified]`.
- `test_save_clears_dirty` — patch QFileDialog.getSaveFileName, call `save_as_protocol_dialog`, assert file written and tracker.is_modified False.
- `test_save_uses_loaded_path_when_set` — after `set_saved("/x.json")`, calling `save_protocol_dialog` writes to `/x.json` without a dialog.
- `test_save_without_loaded_path_falls_back_to_save_as` — after default state, `save_protocol_dialog` invokes the dialog.
- `test_load_clears_dirty_and_sets_path` — patch QFileDialog + provide a fixture JSON, call `load_protocol_dialog`, assert tracker reflects loaded protocol.
- `test_load_aborts_on_user_no_when_dirty` — patch `confirm` to return NO, assert no file dialog is opened and manager untouched.
- `test_new_protocol_resets_tracker_and_manager` — load a protocol, then `new_protocol` after NO is confirmed; ensure manager.root has no children and tracker reset.
- `test_application_exiting_vetos_on_dirty_no` — fake `application_exiting` event with `veto` attribute, dirty manager, mock confirm to NO; assert event.veto True.

## 6. Manual smoke

1. `python examples/run_device_viewer_pluggable.py`
2. Open `&Protocol` menu — see four entries.
3. Edit a step → title shows `Pluggable Protocol Tree - untitled [modified]`.
4. `Save &as` → choose path → title becomes `Pluggable Protocol Tree - <name>`.
5. Edit again → title gets `[modified]` back.
6. `&Save` → title returns to clean.
7. With unsaved edits, `&Load` → confirm dialog appears; NO aborts.
8. With unsaved edits, close window → confirm dialog appears; NO keeps the app open.

## 7. Risks & open questions

- **Veto plumbing on `application_exiting`.** Envisage's `application_exiting` is an `Event(Vetoable)`. Test environment will fake the event object. Worst case: if veto plumbing differs in this version of Envisage, the app-exit guard becomes a "log + warn" instead of a hard veto — degraded but not broken. Will be verified during implementation.
- **Save path encoding on Windows.** `QFileDialog` returns backslashed paths on Windows. `Path(p).stem` handles both — no special-case needed. Tests use `Path` consistently.
- **Concurrent dirty flag flipping during executor highlight events.** `RowManager.rows_changed` does NOT fire on selection changes or highlight, only on structure/value mutations — verified by reading row_manager.py. So executor-driven UI does not falsely dirty the protocol.
