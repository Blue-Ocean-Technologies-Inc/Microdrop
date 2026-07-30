# Idle Phase Navigation (#493) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An opt-in "Phase navigation" mode — a checkbox synced between the device viewer sidebar and the protocol tree — that lets the user step/scrub through the selected step's route phases while no protocol is running, with hardware actuation gated on realtime mode.

**Architecture:** Device-viewer-led (spec `docs/superpowers/specs/2026-07-29-idle-phase-navigation-design.md`). The DV's existing `RouteExecutionService` becomes the single idle stepping engine; the protocol tree acts as a remote control over three pub/sub topics (mode, request, state). The paused-mid-run seek stack (#471/#477) is untouched.

**Tech Stack:** Traits/TraitsUI + PySide6, Dramatiq pub/sub (`publish_message` / listener actors), existing `PathExecutionService` phase math.

## Global Constraints

- Repo: work in the Microdrop submodule (`microdrop-py/src`), branch `feat/493-idle-phase-navigation` (already created from `origin/main`).
- Commit messages MUST be Conventional Commits (`feat(scope): subject`, imperative, ~50 chars); commit-msg hook enforces this.
- **Testing convention (project owner's rule, overrides TDD):** do NOT write or run pytest suites for this feature. Verification per task = byte-compile the touched files + the import smoke command given in each task. The owner tests the GUI manually (final checklist in Task 6).
- Compile/import check command shape (run from `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py`):
  `pixi run python -m py_compile src/<file> [src/<file> ...]`
- f-strings everywhere, including log messages. Never `%s` / `.format()`.
- No cross-plugin references: tree ↔ DV communicate ONLY via topics; constants-only cross-imports are sanctioned (`pluggable_protocol_tree.consts` already imports from `device_viewer.consts`).
- Do not alias constants to new names; import and use them as defined.

---

### Task 1: Topics, model trait, and mode sync (device viewer side)

**Files:**
- Modify: `device_viewer/consts.py` (topics after `ROUTES_EXECUTING`, ~line 39; `ACTOR_TOPIC_DICT` ~line 79)
- Modify: `device_viewer/models/main_model.py` (mode-properties block, ~line 88)
- Modify: `device_viewer/views/device_view_dock_pane.py` (imports ~line 75; traits ~line 151; handlers ~line 240; observers ~line 578)

**Interfaces:**
- Consumes: existing `publish_message`, `GUI.invoke_later`, `basic_listener_actor_routine` reflective dispatch (`_on_{last_topic_segment}_triggered`).
- Produces: topic constants `PHASE_NAVIGATION_MODE = "ui/phase_navigation_mode"`, `PHASE_NAVIGATION_REQUEST = "ui/device_viewer/phase_navigation_request"`, `PHASE_NAVIGATION_STATE = "ui/device_viewer/phase_navigation_state"`; model trait `DeviceViewMainModel.phase_navigation_mode: Bool(False)`. Tasks 2-5 rely on these exact names.

- [ ] **Step 1: Add the topic constants**

In `device_viewer/consts.py`, directly under the `ROUTES_EXECUTING` block (after line 39):

```python
# Idle phase-navigation mode (#493): opt-in checkbox synced between the DV
# sidebar and the protocol tree. Payload "True"/"False". Published by
# whichever UI the user toggled; both subscribe (applying an equal value is
# a trait no-op, so echoes are harmless).
PHASE_NAVIGATION_MODE          = "ui/phase_navigation_mode"
# Tree -> DV: navigate while idle-stepping. JSON payload:
# {"action": "prev" | "next" | "goto", "index": <int, goto only>}.
PHASE_NAVIGATION_REQUEST       = "ui/device_viewer/phase_navigation_request"
# DV -> tree: current idle-nav position. JSON payload:
# {"phase_index": <0-based int>, "phase_total": <int>}; total 0 = no plan.
PHASE_NAVIGATION_STATE         = "ui/device_viewer/phase_navigation_state"
```

In the same file, add to `ACTOR_TOPIC_DICT[listener_name]` (the DV subscribes to mode toggles and nav requests; it only *publishes* state):

```python
        PHASE_NAVIGATION_MODE,
        PHASE_NAVIGATION_REQUEST,
```

Note the dispatch rule already documented at line 73: the listener dispatches on `topic.split("/")[-1]`, so these map to `_on_phase_navigation_mode_triggered` / `_on_phase_navigation_request_triggered` — both last segments are unique across the dict.

- [ ] **Step 2: Add the model trait**

In `device_viewer/models/main_model.py`, in the "mode properties" block right after `free_mode = Bool(True)` (line 88):

```python
    # Idle phase-navigation mode (#493): step through the selected step's
    # route phases while no protocol runs. Synced with the protocol tree
    # over PHASE_NAVIGATION_MODE.
    phase_navigation_mode = Bool(False)
```

- [ ] **Step 3: Wire mode sync in the dock pane**

In `device_viewer/views/device_view_dock_pane.py`:

Extend the consts import at line 75 to include the new topic (requests are handled in Task 3; import all three now):

```python
from ..consts import DEVICE_VIEWER_STATE_CHANGED, DEVICE_VIEWER_GEOMETRY_CHANGED, FILLER_CAPACITANCE_KEY, \
    LIQUID_CAPACITANCE_KEY, CALIBRATION_DATA, STEP_PARAMS_COMMIT, \
    PHASE_NAVIGATION_MODE
```

Add a guard trait next to `_disable_state_messages` (~line 152):

```python
    _applying_phase_nav_message = Bool(False, desc="True while applying an inbound PHASE_NAVIGATION_MODE message, so the publish observer doesn't rebroadcast it")
```

Add the inbound handler near `_on_realtime_mode_updated_triggered` (~line 240). It marshals to the GUI thread because flipping the mode drives `RouteExecutionService` (Task 2), which mutates `actuated_channels` and touches its QTimer:

```python
    def _on_phase_navigation_mode_triggered(self, message):
        GUI.invoke_later(
            self._apply_phase_navigation_mode, message.lower() == "true")

    def _apply_phase_navigation_mode(self, enabled):
        if self.model is None:
            return
        self._applying_phase_nav_message = True
        try:
            self.model.phase_navigation_mode = enabled
        finally:
            self._applying_phase_nav_message = False
```

Add the outbound publish + run-start force-exit observers near `publish_model_message` (~line 594):

```python
    @observe("model.phase_navigation_mode")
    def _publish_phase_navigation_mode(self, event):
        # User toggled the sidebar checkbox (or the mode was force-exited):
        # broadcast so the protocol tree's checkbox follows. Inbound messages
        # set _applying_phase_nav_message so they are not re-broadcast.
        if not self._applying_phase_nav_message:
            publish_message(topic=PHASE_NAVIGATION_MODE, message=str(event.new))

    @observe("model.protocol_running")
    def _exit_phase_navigation_on_run(self, event):
        # A protocol run owns the hardware: force the idle mode off (this
        # publishes "False" via the observer above, unchecking both UIs).
        if event.new and self.model.phase_navigation_mode:
            self.model.phase_navigation_mode = False
```

- [ ] **Step 4: Compile check**

Run (from `microdrop-py/`):
`pixi run python -m py_compile src/device_viewer/consts.py src/device_viewer/models/main_model.py src/device_viewer/views/device_view_dock_pane.py`
Expected: exit 0, no output.

- [ ] **Step 5: Commit**

```bash
git add device_viewer/consts.py device_viewer/models/main_model.py device_viewer/views/device_view_dock_pane.py
git commit -m "feat(device-viewer): phase-navigation topics and synced mode trait (#493)"
```

---

### Task 2: Idle stepping engine in RouteExecutionService

**Files:**
- Modify: `device_viewer/services/route_execution_service.py`
- Modify: `device_viewer/interfaces/i_route_execution_service.py`

**Interfaces:**
- Consumes: `PHASE_NAVIGATION_STATE` from `device_viewer/consts.py` (Task 1); `model.phase_navigation_mode` (Task 1); existing `_apply_phase`, `_execution_plan`, `_current_phase_index` conventions (index always points at the NEXT phase; displayed phase is index-1).
- Produces: public methods `rebuild_phase_navigation()` and `goto_phase(index: int)` (0-based absolute), used by the dock pane in Task 3. Publishes `PHASE_NAVIGATION_STATE` JSON `{"phase_index": int, "phase_total": int}` on every idle-nav change. `goto_prev_phase`/`goto_next_phase` now also work when idle-nav is in charge.

- [ ] **Step 1: Imports**

In `device_viewer/services/route_execution_service.py` add `import json` at the top and extend the consts import (line 6):

```python
import json
```
```python
from ..consts import ROUTES_EXECUTING, PHASE_NAVIGATION_STATE
```

- [ ] **Step 2: Extract the plan builder (DRY with the playback path)**

Replace lines 81-106 of `_execute_path_requested_change` (from `# Build paths from route layers` through the `plan = PathExecutionService.calculate_execution_plan_from_params(...)` call) with:

```python
        # Build paths from route layers (kept for the rep breakdown below)
        paths = [layer.route.route for layer in routes_to_execute]

        linear_repeats = bool(self.model.routes.linear_repeats)

        plan = self._build_execution_plan(routes_to_execute)
```

and add the extracted helper right after `_capture_user_changes` (keep the existing comments' content):

```python
    def _build_execution_plan(self, routes_to_execute):
        """Phase plan for the given layers from the live sidebar params.
        Shared by timed playback and idle phase navigation (#493)."""
        paths = [layer.route.route for layer in routes_to_execute]

        # Currently activated electrode IDs (individually selected, not part
        # of routes) ride along in every phase.
        activated_electrode_ids = []
        for channel in self.model.electrodes.actuated_channels:
            if channel in self.model.electrodes.channels_electrode_ids_map:
                activated_electrode_ids.extend(
                    self.model.electrodes.channels_electrode_ids_map[channel])

        return PathExecutionService.calculate_execution_plan_from_params(
            duration=self.model.routes.duration,
            repetitions=self.model.routes.repetitions,
            repeat_duration=self.model.routes.repeat_duration,
            trail_length=self.model.routes.trail_length,
            trail_overlay=self.model.routes.trail_overlay,
            paths=paths,
            activated_electrodes=activated_electrode_ids,
            soft_start=self.model.routes.soft_start,
            soft_terminate=self.model.routes.soft_terminate,
            linear_repeats=bool(self.model.routes.linear_repeats),
        )
```

(The old inline `activated_electrode_ids` loop and the `linear_repeats` sourcing comment move into the helper; `_execute_path_requested_change` keeps using its local `linear_repeats` for the rep-breakdown call.)

- [ ] **Step 3: Mode lifecycle + rebuild**

Add after the `_on_next_phase_requested` observer (line 169):

```python
    # ----------------------- Idle phase navigation (#493) -------------------

    @observe("model:phase_navigation_mode")
    def _phase_navigation_mode_changed(self, event):
        if event.new:
            self.start_phase_navigation()
        else:
            self.stop_phase_navigation()

    def _nav_active(self):
        """Idle phase navigation is in charge: mode on, no timed playback."""
        return (self.model.phase_navigation_mode
                and not self.model.route_execution_service_executing)

    def start_phase_navigation(self):
        if self.model.route_execution_service_executing:
            self.stop_execution()
        self.rebuild_phase_navigation()

    def stop_phase_navigation(self):
        if self.model.route_execution_service_executing:
            return  # timed playback owns the display; nothing to restore
        if self._execution_plan:
            # Drop the applied phase, keep what the user toggled themselves.
            self.model.electrodes.actuated_channels = self._user_toggled_channels
        self._execution_plan = []
        self._current_phase_index = 0
        self._last_set_channels = set()
        self._user_toggled_channels = set()
        self.model.execution_status = ""
        self._publish_phase_nav_state()

    def rebuild_phase_navigation(self):
        """(Re)build the idle-nav plan from the play-enabled layers and show
        phase 0. Called on mode entry, on step selection change (dock pane),
        and on play-checkbox / execution-param edits. No-op unless idle
        navigation is in charge."""
        if not self._nav_active():
            return
        if self._execution_plan:
            # Restore the user baseline before re-snapshotting it, so the
            # previous plan's phase electrodes don't leak into the new plan.
            self.model.electrodes.actuated_channels = self._user_toggled_channels
        routes_to_execute = [layer for layer in self.model.routes.layers
                             if layer.selected_for_run]
        plan = (self._build_execution_plan(routes_to_execute)
                if routes_to_execute else [])
        self._user_toggled_channels = set(self.model.electrodes.actuated_channels)
        self._last_set_channels = set(self.model.electrodes.actuated_channels)
        self._execution_plan = plan
        self._current_phase_index = 0
        if plan:
            logger.info(f"Idle phase navigation: plan rebuilt, {len(plan)} phases")
            self._apply_phase(plan[0])
            self._update_phase_rep_status(0)
            self._current_phase_index = 1
        else:
            self.model.execution_status = ""
        self._publish_phase_nav_state()

    def _publish_phase_nav_state(self):
        displayed = (self._current_phase_index - 1) if self._execution_plan else 0
        publish_message(
            topic=PHASE_NAVIGATION_STATE,
            message=json.dumps({
                "phase_index": max(0, displayed),
                "phase_total": len(self._execution_plan),
            }))
```

Also add rebuild-on-edit observers right below (play checkbox toggles, param edits):

```python
    @observe("model:routes:layers:items:selected_for_run")
    @observe("model:routes:[duration, repetitions, repeat_duration, "
             "trail_length, trail_overlay, soft_start, soft_terminate, "
             "linear_repeats]")
    def _rebuild_nav_on_edit(self, event):
        self.rebuild_phase_navigation()
```

- [ ] **Step 4: Make the goto methods nav-aware and add goto_phase**

Replace the two existing methods `goto_prev_phase` / `goto_next_phase` (lines 322-359) entirely with:

```python
    def goto_prev_phase(self):
        """Navigate to the previous phase (paused playback or idle nav)."""
        # _current_phase_index points at the NEXT phase, so the displayed
        # phase is index-1 and "previous" is index-2 (goto_phase clamps).
        self.goto_phase(self._current_phase_index - 2)

    def goto_next_phase(self):
        """Navigate to the next phase (paused playback or idle nav)."""
        self.goto_phase(self._current_phase_index)

    def goto_phase(self, index):
        """Jump to absolute 0-based phase ``index`` (clamped into the plan).
        Active while playback is paused or idle navigation is in charge."""
        if not (self.model.route_execution_service_paused or self._nav_active()):
            return
        if not self._execution_plan:
            return

        self._navigated_while_paused = True
        self._capture_user_changes()

        target = max(0, min(int(index), len(self._execution_plan) - 1))
        self._current_phase_index = target
        plan_item = self._execution_plan[self._current_phase_index]
        self._apply_phase(plan_item)
        self._update_phase_rep_status(self._current_phase_index)
        self._current_phase_index += 1  # advance past the displayed phase
        self._phase_timer.stop()  # clear any remaining time from interrupted phase

        if self._nav_active():
            self._publish_phase_nav_state()
```

(Behavior for the paused-playback case is preserved: prev at phase 0 re-applies phase 0, next at the end re-applies the last phase — the old code's clamp/early-return had the same visible effect.)

- [ ] **Step 5: Status label without the playback timer readout**

Replace `_update_phase_rep_status` (lines 238-241) with:

```python
    def _update_phase_rep_status(self, displayed_phase_index):
        """Record displayed phase (0-based) and refresh the status string."""
        self._displayed_phase = displayed_phase_index + 1
        if self._nav_active():
            # No timer/rep readout while idle-stepping — just the position.
            self.model.execution_status = (
                f"Phase: {self._displayed_phase}/{len(self._execution_plan)}")
        else:
            self._update_status_display()
```

- [ ] **Step 6: Re-enter nav mode after a timed playback ends**

At the very end of `_cleanup` (after the `layer.execution_disabled = False` loop):

```python
        # If the user played routes while the idle nav mode was on, hand the
        # display back to phase navigation (#493).
        if self.model.phase_navigation_mode:
            self.rebuild_phase_navigation()
```

- [ ] **Step 7: Mirror the new public methods on the interface**

In `device_viewer/interfaces/i_route_execution_service.py`, extend the goto docstrings and add the new methods after `goto_next_phase`:

```python
    def goto_prev_phase(self):
        """Navigate to the previous phase (paused playback or idle nav)."""

    def goto_next_phase(self):
        """Navigate to the next phase (paused playback or idle nav)."""

    def goto_phase(self, index):
        """Jump to absolute 0-based phase ``index`` (paused or idle nav)."""

    def rebuild_phase_navigation(self):
        """(Re)build the idle phase-navigation plan (#493)."""
```

- [ ] **Step 8: Compile check**

`pixi run python -m py_compile src/device_viewer/services/route_execution_service.py src/device_viewer/interfaces/i_route_execution_service.py`
Expected: exit 0.

- [ ] **Step 9: Commit**

```bash
git add device_viewer/services/route_execution_service.py device_viewer/interfaces/i_route_execution_service.py
git commit -m "feat(device-viewer): idle phase stepping in RouteExecutionService (#493)"
```

---

### Task 3: DV sidebar UI, actuation gate, request handling

**Files:**
- Modify: `device_viewer/views/route_selection_view/route_selection_view.py` (run_controls ~line 174; status bar ~line 221; demo model ~line 253)
- Modify: `device_viewer/views/device_view_dock_pane.py` (imports; `apply_message_model` end ~line 540; `publish_electrode_update` ~line 630; log observer ~line 645; new request handler)

**Interfaces:**
- Consumes: `model.phase_navigation_mode` (Task 1); `route_execution_service.rebuild_phase_navigation()` / `goto_phase(index)` / `goto_prev_phase()` / `goto_next_phase()` (Task 2); `PHASE_NAVIGATION_REQUEST` constant (Task 1).
- Produces: sidebar checkbox bound to `object.phase_navigation_mode`; Prev/Next buttons visible in nav mode; hardware actuation while idle-nav; DV consumes tree nav requests.

- [ ] **Step 1: Sidebar view changes**

In `route_selection_view.py`, add below the `paused` / `executing` name definitions (line 172):

```python
nav_mode = "object.phase_navigation_mode"
```

In `run_controls`, change the two phase buttons' `visible_when` and append the checkbox item before the closing `enabled_when`:

```python
    UItem(
        "object.routes.prev_phase_btn",
        tooltip="Previous phase",
        visible_when=f"{paused} or ({nav_mode} and not {executing})",
        springy=True,
    ),  # previous phase
```
```python
    UItem(
        "object.routes.next_phase_btn",
        tooltip="Next phase",
        visible_when=f"{paused} or ({nav_mode} and not {executing})",
        springy=True,
    ),  # next phase
```
```python
    Item(
        "phase_navigation_mode",
        label="Phases",
        tooltip="Step through route phases without running the protocol "
                "(synced with the protocol tree)",
        visible_when=f"not {executing}",
    ),  # idle phase-navigation mode (#493)
```

Change `execution_status_bar` so the phase counter shows while idle-stepping:

```python
execution_status_bar = HGroup(
    Item('execution_status', style='readonly', show_label=False),
    visible_when=f"{executing} or {nav_mode}",
)
```

In the `__main__` demo's `RouteSelectionDemoModel`, add next to `protocol_running = Bool(False)`:

```python
        phase_navigation_mode = Bool(False)
```

- [ ] **Step 2: Actuation gate fix**

In `device_view_dock_pane.py`, `publish_electrode_update` (line 632), change the condition to:

```python
            if (not self.model.protocol_running
                    and (self.model.free_mode or self.model.phase_navigation_mode)) or (
                    self.model.protocol_running and self.model.editable):
```

And in `_actuation_publish_disabled_log_message` (line 654), replace the free-mode reason with:

```python
        if not self.model.free_mode and not self.model.phase_navigation_mode:
            reason += "Not in free mode or phase navigation; "
```

(also add `@observe("model.phase_navigation_mode")` to that log observer's decorator stack so the diagnostics refresh when the mode flips).

- [ ] **Step 3: Nav request handler**

No new import is needed in `device_view_dock_pane.py`: `PHASE_NAVIGATION_REQUEST` is only the subscription topic (already in `ACTOR_TOPIC_DICT` from Task 1), and the listener dispatches by topic name. Add the handler next to `_on_phase_navigation_mode_triggered`:

```python
    def _on_phase_navigation_request_triggered(self, message):
        # Nav requests drive the route-execution service (actuated_channels +
        # its QTimer), so marshal onto the GUI thread.
        GUI.invoke_later(self._apply_phase_navigation_request, message)

    def _apply_phase_navigation_request(self, message):
        service = self.model.route_execution_service if self.model else None
        if service is None:
            return
        try:
            request = json.loads(message)
        except (ValueError, TypeError) as e:
            logger.warning(f"Bad phase-navigation request {message!r}: {e}")
            return
        action = request.get("action")
        if action == "prev":
            service.goto_prev_phase()
        elif action == "next":
            service.goto_next_phase()
        elif action == "goto":
            service.goto_phase(int(request.get("index", 0)))
        else:
            logger.warning(f"Unknown phase-navigation action: {action!r}")
```

- [ ] **Step 4: Rebuild on step selection change**

At the very end of `apply_message_model` (after `self._publish_geometry_if_changed()`, line 540):

```python
        # Idle phase navigation follows the newly applied step (#493). Runs
        # after _disable_state_messages is cleared so phase 0's actuation
        # publishes (realtime-gated) like any other nav step.
        if self.model.phase_navigation_mode and not self.model.protocol_running:
            self.model.route_execution_service.rebuild_phase_navigation()
```

- [ ] **Step 5: Compile check**

`pixi run python -m py_compile src/device_viewer/views/route_selection_view/route_selection_view.py src/device_viewer/views/device_view_dock_pane.py`
Expected: exit 0. Also smoke the sidebar demo view imports:
`pixi run python -c "import device_viewer.views.route_selection_view.route_selection_view"` run with `bash -c "cd src && ..."` (needs cwd `src/`).
Expected: no traceback.

- [ ] **Step 6: Commit**

```bash
git add device_viewer/views/route_selection_view/route_selection_view.py device_viewer/views/device_view_dock_pane.py
git commit -m "feat(device-viewer): sidebar phase-nav checkbox and idle actuation gate (#493)"
```

---

### Task 4: Protocol tree — sync-controller subscriptions

**Files:**
- Modify: `pluggable_protocol_tree/consts.py` (imports ~line 8; `ACTOR_TOPIC_DICT` ~line 113)
- Modify: `pluggable_protocol_tree/services/device_viewer_sync.py` (traits ~line 209; `_listener_routine` ~line 350)

**Interfaces:**
- Consumes: `PHASE_NAVIGATION_MODE`, `PHASE_NAVIGATION_STATE` from `device_viewer.consts` (Task 1).
- Produces: `DeviceViewerSyncController.phase_nav_mode: Bool`, `.phase_nav_index: Int`, `.phase_nav_total: Int` — observed by the dock pane in Task 5 (worker-thread writes; observers must use `dispatch="ui"`).

- [ ] **Step 1: Subscribe the sync listener**

In `pluggable_protocol_tree/consts.py`, extend the `device_viewer.consts` import (line 8):

```python
from device_viewer.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE, DEVICE_VIEWER_GEOMETRY_CHANGED, \
    DEVICE_VIEWER_STATE_CHANGED, DEVICE_VIEWER_MEDIA_CAPTURED, CALIBRATION_DATA, STEP_PARAMS_COMMIT, \
    PHASE_NAVIGATION_MODE, PHASE_NAVIGATION_REQUEST, PHASE_NAVIGATION_STATE
```

(`PHASE_NAVIGATION_REQUEST` isn't consumed by the sync listener, but importing it here gives the tree package a single constants import site — Task 5's dock pane publishes on it.)

and append both to `ACTOR_TOPIC_DICT[SYNC_LISTENER_NAME]`:

```python
        PHASE_NAVIGATION_MODE,
        PHASE_NAVIGATION_STATE,
```

- [ ] **Step 2: Controller traits + listener branches**

In `pluggable_protocol_tree/services/device_viewer_sync.py`:

Import the two constants (add to the existing consts import block near the top — the module already imports from `pluggable_protocol_tree.consts`; import these from there to keep one import site). Ensure `json` is imported (add `import json` if absent).

Add traits after `advanced_mode` (line 209):

```python
    # Idle phase navigation (#493): mode checkbox state synced over
    # PHASE_NAVIGATION_MODE; position published by the DV engine over
    # PHASE_NAVIGATION_STATE. Written from the dramatiq worker thread —
    # the dock pane observes all three with dispatch="ui".
    phase_nav_mode = Bool(False)
    phase_nav_index = Int(0)
    phase_nav_total = Int(0)
```

Add branches to `_listener_routine` before the `REALTIME_MODE_UPDATED` branch:

```python
        elif topic == PHASE_NAVIGATION_MODE:
            self.phase_nav_mode = (message.casefold() == "true")
        elif topic == PHASE_NAVIGATION_STATE:
            try:
                state = json.loads(message)
                self.trait_set(
                    phase_nav_index=int(state.get("phase_index", 0)),
                    phase_nav_total=int(state.get("phase_total", 0)),
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"bad phase-navigation state {message!r}: {e}")
```

- [ ] **Step 3: Compile check**

`pixi run python -m py_compile src/pluggable_protocol_tree/consts.py src/pluggable_protocol_tree/services/device_viewer_sync.py`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add pluggable_protocol_tree/consts.py pluggable_protocol_tree/services/device_viewer_sync.py
git commit -m "feat(protocol-tree): subscribe to phase-navigation topics (#493)"
```

---

### Task 5: Protocol tree — checkbox, nav bar, timeline wiring

**Files:**
- Modify: `pluggable_protocol_tree/views/navigation_bar.py` (after `merge_phase_controls_to_play_button`, ~line 337)
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py` (`_build_timeline_controls`, ~line 312)
- Modify: `pluggable_protocol_tree/views/dock_pane.py` (imports; `create_contents` wiring ~line 302; `_on_prev_phase`/`_on_next_phase` ~line 458; `_on_timeline_phase_seek` ~line 520; `_refresh_timeline_position` ~line 538; `_update_timeline_controls` ~line 591; new observers near `_on_advanced_mode_changed` ~line 1244)

**Interfaces:**
- Consumes: `sync.phase_nav_mode` / `phase_nav_index` / `phase_nav_total` (Task 4); `PHASE_NAVIGATION_MODE`, `PHASE_NAVIGATION_REQUEST` constants; nav bar `set_phase_navigation_enabled(prev, next)`; `collapse_phase_view`.
- Produces: `NavigationBar.show_idle_phase_controls(visible: bool)`; `ProtocolTreePane.phase_nav_check: QCheckBox`; dock-pane helper `_idle_nav_active() -> bool`.

- [ ] **Step 1: Nav bar — idle phase buttons without the Resume cluster**

`split_play_button_to_phase_controls` hides Play and shows Resume (which drives the executor) — wrong for idle. Add after `merge_phase_controls_to_play_button` in `navigation_bar.py`:

```python
    def show_idle_phase_controls(self, visible):
        """Show the Prev/Next-phase buttons around the Play button for idle
        phase navigation (#493). Unlike split_play_button_to_phase_controls,
        Play stays visible and no Resume appears — there is no paused
        executor to resume. No-op while the paused-run cluster is active."""
        if self._phase_navigation_active:
            return
        self.btn_prev_phase.setVisible(bool(visible))
        self.btn_next_phase.setVisible(bool(visible))
        self.play_phase_container.update()
        self.update()
```

- [ ] **Step 2: Pane — the synced checkbox**

In `protocol_tree_pane.py` `_build_timeline_controls`, after `self.timeline_show_full_check` is added to the layout (line 334) and before `layout.addStretch()`:

```python
        self.phase_nav_check = QCheckBox("Phase navigation")
        self.phase_nav_check.setToolTip(
            "Step through the selected step's route phases without running "
            "the protocol (synced with the device viewer sidebar)")
        layout.addWidget(self.phase_nav_check)
```

- [ ] **Step 3: Dock pane — publish on toggle, helpers, request publishing**

In `dock_pane.py`, import the topic constants (extend the module's existing `pluggable_protocol_tree.consts` import with `PHASE_NAVIGATION_MODE`; import `PHASE_NAVIGATION_REQUEST` from `device_viewer.consts` via the tree consts too — add both to the Task 4 re-export if not already importable, i.e. `from pluggable_protocol_tree.consts import PHASE_NAVIGATION_MODE, PHASE_NAVIGATION_REQUEST`; add `PHASE_NAVIGATION_REQUEST` to the Task 4 import line in consts.py as well). Ensure `json` and `publish_message` are already imported in dock_pane.py (they are — used by `_publish_protocol_running` / electrode clear).

In `create_contents`, next to the other timeline-control connections (line 302):

```python
        pane.phase_nav_check.toggled.connect(self._on_phase_nav_check_toggled)
```

Add near `_publish_protocol_running` (line 769):

```python
    def _idle_nav_active(self):
        """Idle phase navigation drives the phase controls: mode checkbox on
        and no run in progress (a paused run keeps the #471 seek stack)."""
        return bool(self.sync.phase_nav_mode) and not self._is_protocol_active()

    def _on_phase_nav_check_toggled(self, checked):
        # Broadcast only — the checkbox state itself follows the topic echo
        # (single source of truth), same as the DV sidebar checkbox.
        publish_message(topic=PHASE_NAVIGATION_MODE, message=str(bool(checked)))

    def _publish_phase_nav_request(self, request):
        try:
            publish_message(topic=PHASE_NAVIGATION_REQUEST,
                            message=json.dumps(request))
        except Exception as e:
            logger.warning(f"phase-navigation request publish failed: {e}")
```

- [ ] **Step 4: Branch the phase controls into idle-nav requests**

Replace `_on_prev_phase` / `_on_next_phase` (lines 458-462):

```python
    def _on_prev_phase(self):
        if self._idle_nav_active():
            self._publish_phase_nav_request({"action": "prev"})
            return
        self._seek_relative_phase(-1)

    def _on_next_phase(self):
        if self._idle_nav_active():
            self._publish_phase_nav_request({"action": "next"})
            return
        self._seek_relative_phase(+1)
```

Prepend to `_on_timeline_phase_seek` (line 520):

```python
        if self._idle_nav_active():
            # Idle nav shows the full materialized plan (no rep collapse), so
            # the bar's 0-based index maps 1:1 onto the DV plan.
            self._publish_phase_nav_request(
                {"action": "goto", "index": int(phase_index)})
            return
```

- [ ] **Step 5: Feed the timeline + buttons from the DV state**

In `_refresh_timeline_position`, right after `current_row = self._current_step_row()` (line 553), insert:

```python
        if self._idle_nav_active():
            # Idle phase navigation (#493): the DV engine owns the position.
            # Full materialized plan on the phase track — no rep collapse.
            self._timeline_can_collapse = False
            self._timeline_base_count = 0
            self._timeline_base_index = 0
            self._timeline_cur_rep = 1
            total = int(self.sync.phase_nav_total)
            tb.set_position(cur if cur is not None else -1, len(rows),
                            int(self.sync.phase_nav_index),
                            total if total > 1 else 0)
            tb.set_idle_cell(None)
            self._update_timeline_controls(
                current_row,
                collapse_phase_view(total, int(self.sync.phase_nav_index),
                                    total, 1, False))
            return
```

In `_update_timeline_controls` (line 591), make the row host the always-available checkbox: replace

```python
        controls.setVisible(phase_possible or step_possible)
```

with

```python
        nav_available = not bool(model.running) if model else True
        self._pane.phase_nav_check.setVisible(nav_available)
        controls.setVisible(phase_possible or step_possible or nav_available)
```

- [ ] **Step 6: Observe the sync traits**

Add next to `_on_advanced_mode_changed` (line 1244):

```python
    @observe("sync:phase_nav_mode", dispatch="ui", post_init=True)
    def _on_phase_nav_mode_changed(self, event):
        """Mode checkbox toggled anywhere (DV sidebar, this pane, force-exit
        on run start): sync the checkbox, the nav-bar phase buttons and the
        timeline."""
        active = self._idle_nav_active()
        check = getattr(self._pane, "phase_nav_check", None)
        if check is not None:
            check.blockSignals(True)
            check.setChecked(bool(self.sync.phase_nav_mode))
            check.blockSignals(False)
        self._pane.navigation_bar.show_idle_phase_controls(active)
        if active:
            self._update_idle_phase_nav_buttons()
        self._refresh_timeline_position()

    @observe("sync:[phase_nav_index, phase_nav_total]", dispatch="ui", post_init=True)
    def _on_phase_nav_state_changed(self, event):
        if not self._idle_nav_active():
            return
        self._update_idle_phase_nav_buttons()
        self._refresh_timeline_position()

    def _update_idle_phase_nav_buttons(self):
        total = int(self.sync.phase_nav_total)
        index = int(self.sync.phase_nav_index)
        self._pane.navigation_bar.set_phase_navigation_enabled(
            total > 0 and index > 0,
            total > 0 and index < total - 1,
        )
```

- [ ] **Step 7: Compile check**

`pixi run python -m py_compile src/pluggable_protocol_tree/views/navigation_bar.py src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/views/dock_pane.py`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add pluggable_protocol_tree/views/navigation_bar.py pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/views/dock_pane.py
git commit -m "feat(protocol-tree): idle phase-nav checkbox, buttons, timeline (#493)"
```

---

### Task 6: Documentation + manual verification handoff

**Files:**
- Modify: `MESSAGES.md` (repo root of the submodule)

**Interfaces:**
- Consumes: the three topic names and payload schemas from Task 1.
- Produces: documented topics; a manual GUI checklist for the project owner.

- [ ] **Step 1: Document the topics in MESSAGES.md**

Open `MESSAGES.md`, find the topic-map table/listing style plus the "Device Viewer → Protocol Grid: routes / state sync" detailed-flow section, and add matching entries (mirror the exact formatting used by neighbouring entries):

- `ui/phase_navigation_mode` — payload `"True"/"False"`. Published by: `device_viewer/views/device_view_dock_pane.py` (`_publish_phase_navigation_mode`) and `pluggable_protocol_tree/views/dock_pane.py` (`_on_phase_nav_check_toggled`). Subscribed by: both (DV listener `ACTOR_TOPIC_DICT`, tree `SYNC_LISTENER_NAME`). Opt-in idle phase-navigation mode (#493); force-exited (published `"False"`) when a protocol run starts.
- `ui/device_viewer/phase_navigation_request` — JSON `{"action": "prev"|"next"|"goto", "index": int}`. Published by the tree's nav-bar phase buttons / timeline phase track while idle-navigating; consumed by the DV (`_on_phase_navigation_request_triggered` → `RouteExecutionService`).
- `ui/device_viewer/phase_navigation_state` — JSON `{"phase_index": int (0-based), "phase_total": int}` (`phase_total` 0 = no plan). Published by `RouteExecutionService._publish_phase_nav_state`; consumed by the tree sync controller to drive its timeline/buttons.

- [ ] **Step 2: Commit**

```bash
git add MESSAGES.md
git commit -m "docs: document phase-navigation topics (#493)"
```

- [ ] **Step 3: Report the manual GUI checklist to the project owner (do not run it yourself)**

Present this checklist for manual verification (full app + Redis; realtime tests need a DropBot or the mock controller):

1. Select a step with routes → tick "Phases" in the DV sidebar → phase 0 highlights, Prev/Next appear, status shows "Phase: 1/N". The tree's "Phase navigation" checkbox ticks itself.
2. Tick the checkbox from the tree side instead → DV sidebar checkbox follows.
3. Prev/Next in the DV sidebar and in the tree nav bar step the same position; the tree timeline's phase track follows; scrubbing the phase track jumps the DV highlight.
4. Realtime OFF: no hardware actuation messages on stepping (log shows the gate reason). Realtime ON + connected: each step actuates the phase electrodes.
5. Untick a route's Run (play) checkbox → plan rebuilds from remaining routes at phase 0. Edit Duration/Trail Len → same.
6. Select a different step → plan rebuilds for it at phase 0. Select a group row / free mode → controls disable gracefully (total 0).
7. Start a protocol run → both checkboxes clear; paused-run phase seeking (#471) behaves exactly as before; after the run ends the mode stays off until re-ticked.
8. Sidebar Run (timed playback) with mode on → playback works; on stop/finish the display hands back to nav mode at phase 0.

---

## Self-review notes (already applied)

- Spec coverage: mode sync (T1/T4/T5), engine (T2), sidebar UI + actuation gate + requests (T3), tree remote control + full-count timeline (T5), MESSAGES.md (T6), force-exit on run start (T1), rebuild triggers (T2 observers + T3 apply_message_model), no-plan edge (T2 rebuild/goto guards; T5 button enables on total 0).
- Type consistency: `phase_nav_mode/index/total` (sync traits) vs `phase_navigation_mode` (DV model trait) vs topic constants — names match across tasks; request/state JSON keys are `action`/`index` and `phase_index`/`phase_total` everywhere.
- Paused-run path untouched: `_update_phase_nav_buttons`, `_seek_to_phase`, `split_play_button_to_phase_controls` all unchanged; new code only adds early-return branches gated on `_idle_nav_active()` (which is False whenever a run is active).
