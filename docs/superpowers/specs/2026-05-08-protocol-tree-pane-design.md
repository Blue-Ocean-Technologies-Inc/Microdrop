# Protocol Tree Pane — Full-app Dock Pane Refactor

**Issue:** [#411 — PPT-10.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/411)
**Parent:** #361 (PPT)
**Predecessors:** #377 (PPT-10 navigation pane port)
**Successors:** #371 (PPT-9 protocol_grid deletion)
**Date:** 2026-05-08

## Background

PPT-10 (#377) ported `NavigationBar` + `StatusBar` + experiment-bar (new-experiment / experiment-label / new-note) into `pluggable_protocol_tree/views/navigation_bar.py`, and wired all of it into `BasePluggableProtocolDemoWindow` so the demos look and feel like the legacy `protocol_grid`. The full-app dock pane (`pluggable_protocol_tree/views/dock_pane.py`) is still the minimal wrapper from PPT-3 — it only mounts `ProtocolTreeWidget`, with no playback bar, no status bar, and no experiment controls.

Before #371 can delete `protocol_grid`, the dock pane has to host the same scaffolding the legacy widget does **and** the experiment / sticky-note actions need to be wired against the live Envisage services rather than the demo's stub handlers. After this work the new dock pane is usable in the actual full app — not just in the demo windows.

## Goals

1. Extract the demo's standard UX scaffolding into a reusable `ProtocolTreePane(QWidget)` so the demo window and the dock pane mount one instance.
2. Wire experiment-bar actions (New Experiment, experiment-label click, New Note) against the live `ExperimentManager` + `StickyWindowManager` services when those services are supplied.
3. Make `BasePluggableProtocolDemoWindow` a thin shell around `ProtocolTreePane`, while keeping the existing test suite (`test_base_demo_window.py`) green via backward-compatibility aliases.
4. Register `PluggableProtocolTreePlugin` in `examples/plugin_consts.py` so launching the full app shows the new dock pane alongside the legacy `protocol_grid` pane during transition.

## Non-goals

- Removing or modifying the legacy `protocol_grid` plugin (covered by #371).
- Cleaning up `ExperimentManager` and `StickyWindowManager` beyond making them callable from the new dock pane (covered by #371 / PPT-9).
- The Quick-Actions bar (`protocol_grid/quick_action_bar.py`).
- Full message-listener parity with the legacy widget — capacitance overlays, droplet detection feedback, DropBot connection gating, voltage/frequency-range UI updates. Tracked as a follow-up.

## Approach

`ProtocolTreePane(QWidget)` owns everything that's currently in `BasePluggableProtocolDemoWindow.__init__` between the manager construction and the toolbar build:

- Manager + ProtocolTreeWidget
- ProtocolExecutor (+ pause/stop events) + executor-signal wiring
- NavigationBar + StatusBar + ExperimentLabel + experiment-bar buttons
- Phase-navigation pause logic (`_compute_pause_phase_state`, `_on_prev_phase`, `_on_next_phase`, `_publish_paused_phase`)
- Step-cursor navigation (`_navigate_to_first_step` etc.)
- Tick timer + button state machine (`_set_idle_button_state`, `_set_running_button_state`, `_on_protocol_paused`, `_on_protocol_resumed`, etc.)
- Save/Load file pickers

The window keeps:

- Window chrome (title, size)
- `Add Step / Add Group / Save / Load` `QToolBar` (separate from the pane's own internal save/load helpers)
- Side-panel splitter
- Bottom `QStatusBar` per-readout labels (StatusReadout machinery from `DemoConfig`)
- Dramatiq routing setup (broker flush, demo-prefix subscriber purge, electrode chain wiring, phase-ack listener, status-readout listeners)

The dock pane keeps:

- Column assembly from the Envisage extension point
- Service construction (`ExperimentManager`, `StickyWindowManager`)
- Application trait observation for label sync

### Service-injection contract

`ProtocolTreePane` accepts optional service parameters:

```python
ProtocolTreePane(
    columns_or_manager,                # list[IColumn] OR an existing RowManager
    *,
    application=None,                  # MicrodropApplication; observes current_experiment_directory when set
    experiment_manager=None,           # ExperimentManager; if None, New-Exp button logs only
    sticky_manager=None,               # StickyWindowManager; if None, New-Note button logs only
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    executor_factory=None,             # for tests — defaults to ProtocolExecutor(...)
    parent=None,
)
```

Rule: when a service is `None`, the corresponding button keeps the demo's log-only stub behavior. When supplied, the pane connects the real handler. This means demos do not need to change at all — passing no services preserves today's UX exactly.

### Real-service wiring (used by the dock pane)

| Trigger | Stub mode (demo) | Real mode (dock pane) |
|---|---|---|
| `btn_new_exp.clicked` | `logger.info("New Experiment requested")` | `experiment_manager.initialize_new_experiment()` → write to `application.current_experiment_directory` → `experiment_label.update_experiment_id(new_dir.stem)` |
| `experiment_label.clicked` | non-clickable `QLabel` | `experiment_manager.open_experiment_directory()` |
| `btn_new_note.clicked` | `logger.info("New Note requested")` | `sticky_manager.request_new_note(base_dir, experiment_name)` |
| `application.experiment_changed` Event fires | n/a | re-read `application.current_experiment_directory`; `experiment_label.update_experiment_id(new_dir.stem)` |

The pane uses the legacy promoted `ExperimentLabel` (clickable, theme-aware link colour, tooltip-toggle context menu) — ported to `pluggable_protocol_tree/views/experiment_label.py`. It stays clickable in stub mode (the disconnected click is a harmless no-op), so demos get the same visual UX.

### Dock-pane sketch

```python
class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = "Protocol (pluggable)"   # renamed during legacy coexistence
    columns = List(Instance(IColumn))

    def create_contents(self, parent):
        from protocol_grid.services.experiment_manager import ExperimentManager
        from microdrop_utils.sticky_notes import StickyWindowManager
        from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

        app = self.task.window.application
        return ProtocolTreePane(
            self.columns,
            application=app,
            experiment_manager=ExperimentManager(app.current_experiment_directory),
            sticky_manager=StickyWindowManager(),
            parent=parent,
        )
```

The legacy `ExperimentManager` import crosses package boundaries intentionally — issue #411 explicitly defers `ExperimentManager` cleanup to PPT-9 (#371).

### Demo-window slimming

`BasePluggableProtocolDemoWindow.__init__` shrinks to:

```python
self.pane = ProtocolTreePane(
    self.config.columns_factory(),
    phase_ack_topic=self.config.phase_ack_topic,
    parent=self,
)
self.config.pre_populate(self.pane.manager)
self._build_central(self.pane)         # wraps pane in side-panel splitter if configured
self._build_toolbar()                  # window-only: Add Step/Group, Save, Load
self._build_status_readouts()          # window-only: bottom QStatusBar readout labels
self._setup_dramatiq_routing_internal()
self.config.routing_setup(self._router)
self.config.post_build_setup(self)
```

#### Backward-compatibility aliases

`test_base_demo_window.py` reaches into many private attributes. The window keeps these accessible via `@property` shims that forward to `self.pane.*`:

| Attribute | Source after refactor |
|---|---|
| `manager`, `widget`, `executor`, `navigation_bar`, `status_bar` | `self.pane.<name>` |
| `_status_step_label`, `_status_step_time_label`, `_status_reps_label`, `_status_phase_time_label` | `self.pane.<name>` |
| `_tick_timer`, `_step_index`, `_step_total`, `_current_row`, etc. | `self.pane.<name>` |
| `btn_new_exp`, `btn_new_note`, `experiment_label` | `self.pane.<name>` |
| `phase_acked` (Qt Signal) | `self.pane.phase_acked` |
| `_central_content`, `_side_panel`, `_toolbar`, `_router` | window (unchanged) |
| `_readout_labels`, `_readout_signals`, `_readout_fmts`, `readout_acked` | window (unchanged — readouts are demo-only) |
| `_clear_all_highlights` | window method that calls `self.pane.clear_highlights()` then resets readouts |

Result: every existing test in `test_base_demo_window.py` keeps passing without test edits.

### Plugin registration

Uncomment in `examples/plugin_consts.py`:

```python
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
...
FRONTEND_PLUGINS = [
    ...
    PluggableProtocolTreePlugin,   # was commented out
    ...
]
```

Both dock panes now mount at app start. The user can drag/dock either independently. Pane title rename to **"Protocol (pluggable)"** during transition keeps the two unambiguous in the dock-pane menu.

### File layout

```
pluggable_protocol_tree/
├── views/
│   ├── protocol_tree_pane.py        # NEW — ProtocolTreePane(QWidget)
│   ├── experiment_label.py          # NEW — ported from protocol_grid/extra_ui_elements.py
│   ├── dock_pane.py                 # MODIFIED — wires real services
│   └── navigation_bar.py            # unchanged
├── demos/
│   └── base_demo_window.py          # SHRINKS — delegates to ProtocolTreePane
└── tests/
    ├── test_protocol_tree_pane.py   # NEW — pane construction + handler wiring
    ├── test_dock_pane.py            # NEW — dock-pane service construction + wiring
    └── test_base_demo_window.py     # MODIFIED — passes via delegation
```

## Data flow

Run-button click in the dock pane:

```
Play click
  → ProtocolTreePane._on_play_clicked
  → ProtocolExecutor.start(start_step_path, preview_mode)
  → executor publishes ELECTRODES_STATE_CHANGE per phase
  → device viewer overlays electrodes (existing subscriber, unchanged)
  → backend ack ELECTRODES_STATE_APPLIED → phase_acked signal → tick timer + status bar
  → on protocol end: button machine returns to idle; auto-repeat re-fires if configured
```

No new message topics are introduced. The pane reuses the same `ProtocolExecutor` and the same electrode chain that the demo already drives. Coexistence with `protocol_grid` is safe because only one pane runs a protocol at a time; both publish to the same topics; both observe `current_experiment_directory`, so they stay in sync.

## Error handling

- `protocol_error` → `ProtocolTreePane._on_error` resets repeat state, clears highlights, returns to idle button state, stops tick timer, shows a styled error dialog via `microdrop_application.dialogs.pyface_wrapper.error` (project convention).
- Missing services (None passed for `experiment_manager` / `sticky_manager`) → button click logs only; never raises.
- `ExperimentManager.initialize_new_experiment()` returning `None` (it logs and swallows on failure) → label is left unchanged; do not write `None` back to `application.current_experiment_directory`. (Match legacy behavior at `widget.py:1022`.)

## Testing strategy

`test_protocol_tree_pane.py`:

- `test_constructs_with_columns_list` — passing a list builds an internal RowManager.
- `test_constructs_with_existing_manager` — passing a RowManager skips the construction step.
- `test_stub_mode_buttons_are_no_ops` — `btn_new_exp.click()` / `btn_new_note.click()` do not raise when no services supplied; logs only.
- `test_real_mode_new_exp_calls_service` — with a `Mock(spec=ExperimentManager)`, click dispatches to `initialize_new_experiment()` and writes back to `application.current_experiment_directory`.
- `test_real_mode_new_note_calls_service` — `Mock(spec=StickyWindowManager).request_new_note` called with `(base_dir, experiment_name)`.
- `test_real_mode_label_click_opens_directory` — `experiment_label.clicked` → `experiment_manager.open_experiment_directory()`.
- `test_application_trait_observed_updates_label` — setting `application.current_experiment_directory` triggers `experiment_label.update_experiment_id(new_dir.stem)`.
- `test_initialize_returns_none_does_not_overwrite_app_dir` — when `initialize_new_experiment()` returns None, `application.current_experiment_directory` is not overwritten.

`test_dock_pane.py`:

- `test_create_contents_returns_protocol_tree_pane` — assert returned widget is a `ProtocolTreePane`.
- `test_create_contents_passes_application_to_pane` — mock task/window/application chain.
- `test_create_contents_constructs_experiment_manager` — `ExperimentManager` is constructed with `app.current_experiment_directory`.
- `test_create_contents_constructs_sticky_manager` — `StickyWindowManager` is constructed once.

`test_base_demo_window.py`:

- All existing tests keep passing without edits, validated via the alias `@property` shims.

Tests live under `pluggable_protocol_tree/tests/` (no Redis or hardware dependencies). Run via `pixi run pytest microdrop-py/src/pluggable_protocol_tree/tests/`.

## Acceptance criteria

- [ ] New `pluggable_protocol_tree/views/protocol_tree_pane.py` defines `ProtocolTreePane(QWidget)` hosting NavigationBar + StatusBar + ProtocolTreeWidget + experiment-bar + ProtocolExecutor with the wiring points listed above.
- [ ] New `pluggable_protocol_tree/views/experiment_label.py` ports the legacy clickable, theme-aware `ExperimentLabel`.
- [ ] `PluggableProtocolDockPane.create_contents` constructs a `ProtocolTreePane` and connects the experiment-manager / sticky-note / experiment-folder handlers via the Envisage application services.
- [ ] `BasePluggableProtocolDemoWindow` delegates to `ProtocolTreePane` rather than building the scaffolding inline. Existing `test_base_demo_window.py` keeps passing without edits.
- [ ] `examples/plugin_consts.py` registers `PluggableProtocolTreePlugin` alongside `ProtocolGridControllerUIPlugin`. The pluggable dock-pane title is "Protocol (pluggable)" so it's unambiguous in the dock-pane menu.
- [ ] Launching `examples/run_device_viewer_pluggable.py` shows both panes; the new pane has working playback + experiment controls including a New Experiment click that creates an experiment via the live `experiment_manager`, a New Note click that opens a sticky note, and an experiment-label click that opens the experiment directory.
- [ ] New tests cover `ProtocolTreePane` construction, experiment-bar handler wiring (with mocked services), application-trait observation, and the dock-pane's service construction.

## Risks & non-obvious bits

- **`StickyWindowManager()` is a singleton-ish manager.** Creating one in the dock pane while the legacy widget creates another is harmless — both manage independent windows. After PPT-9 deletion, only the new one remains.
- **`ExperimentManager._register_cleanup_on_exit`** connects to `app.aboutToQuit`. Two managers register two cleanup hooks pointing at the same parent dir; the underlying `shutil.rmtree` of an empty dir is idempotent so this is harmless until PPT-9 unifies them.
- **`application.current_experiment_directory` is a Traits `Property`** (`microdrop_application/application.py:105`), but the application also exposes a sibling `experiment_changed = Event()` trait (line 106) that the setter `_set_current_experiment_directory` fires (line 185). The pane observes `experiment_changed` instead of the Property directly — Property notifications are unreliable, the Event is what the application explicitly publishes for this purpose. After receiving the event, the pane re-reads `application.current_experiment_directory` to get the new value.
- **Coexistence of two panes during transition** means a user could click Play on both. The existing executor design starts work on a worker thread, and clicking Play on the legacy pane while the new one is running will fire its own ELECTRODES_STATE_CHANGE messages on top — UX issue but not a data-corruption issue. We will not add cross-pane locking; legacy will be removed in #371.
- **Issue #411 wording uses `experiment_manager.setup_new_experiment(...)`.** The actual API on `ExperimentManager` is `initialize_new_experiment()` (`protocol_grid/services/experiment_manager.py:97`). The spec follows the actual API.
