# Status-Bar Extension Point Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Status-bar icons become Envisage extension-point contributions managed by one new `microdrop_status_bar` plugin — no dock pane ever touches the `QStatusBar` directly, spacing is uniform by construction, and hot load/unload cleans the bar automatically.

**Architecture:** A new `StatusBarPlugin` declares a `status_bar_icons` extension point and observes contribution deltas exactly the way `MessageRouterPlugin` observes `actor_topic_routing` (`connect_extension_point_traits()` + `@on_trait_change("<name>_items")`). It creates the window's `StatusBarManager` (moved out of `MicrodropTask.activated()`) and appends a single icon-container widget whose `QHBoxLayout` spacing gives every icon the same gap. `BaseStatusDockPane` contributes its widgets by extending its own plugin's `status_bar_icons = List(contributes_to=...)` trait (declared once on `BaseStatusPlugin`) and withdraws them in teardown.

**Tech Stack:** Envisage (Plugin, ExtensionPoint), Traits (`observe`, `on_trait_change`), Pyface/PySide6 (`QStatusBar`, `QWidget`, `QHBoxLayout`).

**Spec:** `docs/superpowers/specs/2026-07-03-status-bar-extension-point-design.md`

## Global Constraints

- f-strings everywhere, including log messages — never `%s` / `.format()`.
- Logging via `from logger.logger_service import get_logger; logger = get_logger(__name__)`.
- No cross-plugin references — plugins communicate via extension points / app globals only.
- Testing is **manual** (project preference — do NOT run pytest or launch the app yourself); each task ends at "code compiles + committed", and Task 6 is the human verification checklist.
- Qt imports come from `pyface.qt.QtGui` (project convention in `template_status_and_controls/base_dock_pane.py`).
- Work happens in the `microdrop-py/src` git repo (the submodule), branch `status_bar_contribution_extention_point`. Note: `microdrop_application/task.py` has a small pre-existing uncommitted user edit (inlining `_add_status_bar_to_window`) — Task 4 replaces that whole block anyway; do not revert unrelated working-tree changes.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `microdrop_status_bar` plugin package

**Files:**
- Create: `microdrop_status_bar/__init__.py`
- Create: `microdrop_status_bar/consts.py`
- Create: `microdrop_status_bar/plugin.py`

**Interfaces:**
- Consumes: `microdrop_utils.pyface_helpers.StatusBarManager` (existing).
- Produces: extension-point id constant `microdrop_status_bar.consts.STATUS_BAR_ICONS = "status_bar_icons"` (Task 2 imports it); `microdrop_status_bar.plugin.StatusBarPlugin` (Task 5 registers it). Contributed items are QWidget instances; once contributed, this plugin owns their placement AND their deletion (`deleteLater()` on removal).

- [ ] **Step 1: Create the package**

`microdrop_status_bar/__init__.py` — empty file.

`microdrop_status_bar/consts.py`:

```python
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Extension-point id: QWidget instances to show in the app status bar.
STATUS_BAR_ICONS = "status_bar_icons"

#: Uniform gap (px) between adjacent contributed status-bar icons.
ICON_SPACING = 10

#: Status-bar message shown from startup until something replaces it.
DEFAULT_STATUS_MESSAGE = "Free Mode"

#: Contents margins (left, top, right, bottom) of the status bar.
STATUS_BAR_CONTENTS_MARGINS = (30, 0, 30, 0)
```

- [ ] **Step 2: Write the plugin**

`microdrop_status_bar/plugin.py`:

```python
"""
StatusBarPlugin — the one home for the application status bar.

Creates the window's StatusBarManager and owns the ``status_bar_icons``
extension point: other plugins contribute QWidget instances (typically at
runtime, from their dock panes) and this plugin places them in a single
icon container whose QHBoxLayout gives every icon the same gap. Removing
a widget from the extension point removes it from the bar and deletes it.

Dynamic contribution handling mirrors MessageRouterPlugin: apply the
current extensions once the container exists, then react to
``<name>_items`` delta events for runtime (hot load/unload) changes.
"""
from envisage.api import ExtensionPoint, Plugin
from pyface.qt.QtGui import QHBoxLayout, QWidget
from traits.api import Any, List, observe, on_trait_change

from logger.logger_service import get_logger
from microdrop_utils.pyface_helpers import StatusBarManager

from .consts import (
    DEFAULT_STATUS_MESSAGE,
    ICON_SPACING,
    PKG,
    PKG_name,
    STATUS_BAR_CONTENTS_MARGINS,
    STATUS_BAR_ICONS,
)

logger = get_logger(__name__)


class StatusBarPlugin(Plugin):
    """Creates the app status bar and manages contributed status icons."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    status_bar_icons = ExtensionPoint(
        List(),
        id=STATUS_BAR_ICONS,
        desc="QWidget instances to show in the app status bar; this plugin "
             "owns their placement, spacing, and removal",
    )

    #: Single container appended to the status bar; its HBox layout gives
    #: every contributed icon the same gap.
    _icon_container = Any(None)

    def start(self):
        # Wire the registry's extension-point listeners to this plugin's
        # traits so the handlers below fire when contributions change at
        # runtime. Opt-in (envisage never calls it for you), and only
        # possible once the plugin is attached to the application.
        self.connect_extension_point_traits()

    @observe("application:active_window")
    def _setup_status_bar(self, event):
        """Build the status bar on the first window; later re-fires no-op."""
        window = event.new
        if window is None or self._icon_container is not None:
            return
        if window.status_bar_manager is None:
            window.status_bar_manager = StatusBarManager(
                messages=[DEFAULT_STATUS_MESSAGE], size_grip=True
            )
        status_bar = window.status_bar_manager.status_bar
        status_bar.setContentsMargins(*STATUS_BAR_CONTENTS_MARGINS)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ICON_SPACING)
        # Appended, i.e. rightmost — so the joystick indicator's deferred
        # insert at the first permanent slot stays LEFT of every
        # contributed icon (see StatusBarManager.attach_gamepad_indicator).
        status_bar.addPermanentWidget(container)
        self._icon_container = container

        # Contributions made before the window existed already sit in the
        # extension point — apply them now; the _items handler below keeps
        # the bar in sync from here on.
        self._apply_icon_changes(added=self.status_bar_icons, removed=[])

    # ------------------------------------------------------------------ #
    # Extension-point sync                                                 #
    # ------------------------------------------------------------------ #

    def _apply_icon_changes(self, added, removed):
        """Apply contribution deltas to the icon container."""
        if self._icon_container is None:
            return  # no window yet; current extensions applied at setup
        layout = self._icon_container.layout()
        for widget in removed:
            try:
                layout.removeWidget(widget)
                widget.deleteLater()
            except RuntimeError as e:
                logger.debug(f"status-bar icon already deleted: {e}")
        for widget in added:
            layout.addWidget(widget)
        logger.info(
            f"status bar icons changed: +{len(added)} -{len(removed)}; "
            f"{layout.count()} in the bar"
        )

    @on_trait_change("status_bar_icons_items")
    def _on_status_bar_icons_items_changed(self, event):
        """A contribution changed while the app is running.

        Plugin-driven changes (a contributing plugin mutating its
        contribution trait, plugins added/removed from the manager) always
        carry an index, which ExtensionPoint.connect surfaces as this
        synthetic "<name>_items" property event. No real
        ``status_bar_icons_items`` trait exists, so the string-matched
        on_trait_change must bind it — observe() rejects unknown names.
        """
        self._apply_icon_changes(event.added, event.removed)

    @observe("status_bar_icons")
    def _on_status_bar_icons_replaced(self, event):
        """Index-less wholesale replacement of the extension point
        (registry.set_extensions) — never fired for plugin contribution
        changes; covered for completeness."""
        self._apply_icon_changes(added=event.new, removed=event.old)
```

- [ ] **Step 3: Syntax check**

Run: `python -c "import ast; ast.parse(open('microdrop_status_bar/plugin.py').read()); ast.parse(open('microdrop_status_bar/consts.py').read())"` from `microdrop-py/src`.
Expected: no output (exit 0).

- [ ] **Step 4: Commit**

```bash
git add microdrop_status_bar
git commit -m "feat: microdrop_status_bar plugin with status_bar_icons extension point"
```

---

### Task 2: Contribution trait on `BaseStatusPlugin`

**Files:**
- Modify: `template_status_and_controls/base_plugin.py`

**Interfaces:**
- Consumes: `microdrop_status_bar.consts.STATUS_BAR_ICONS` (Task 1).
- Produces: `BaseStatusPlugin.status_bar_icons` (a `List(contributes_to=STATUS_BAR_ICONS)`, empty by default) — Task 3's pane code extends/removes items on this trait. All five device plugins (dropbot, opendrop, mock, heater, magnet) inherit it; no per-device edits.

- [ ] **Step 1: Add the import and trait**

In `template_status_and_controls/base_plugin.py`, after the existing import
`from message_router.consts import ACTOR_TOPIC_ROUTES` add:

```python
from microdrop_status_bar.consts import STATUS_BAR_ICONS
```

In the class body, right after `actor_topic_routing = List(contributes_to=ACTOR_TOPIC_ROUTES)` (line 71) add:

```python
    #: Status-bar widgets contributed at runtime: BaseStatusDockPane
    #: extends this list when it populates the bar; the
    #: microdrop_status_bar plugin places, spaces, and removes them.
    status_bar_icons = List(contributes_to=STATUS_BAR_ICONS)
```

Also extend the module docstring's boilerplate list (lines 5-6) with a third bullet:

```
  - status_bar_icons             (runtime status-bar icon contributions)
```

- [ ] **Step 2: Commit**

```bash
git add template_status_and_controls/base_plugin.py
git commit -m "feat: BaseStatusPlugin contributes to status_bar_icons extension point"
```

---

### Task 3: `BaseStatusDockPane` contributes instead of inserting

**Files:**
- Modify: `template_status_and_controls/base_dock_pane.py`

**Interfaces:**
- Consumes: `BaseStatusPlugin.status_bar_icons` (Task 2), resolved via `self.task.window.application.get_plugin(self.status_bar_plugin_id)`.
- Produces: unchanged factory hooks (`_create_status_bar_icon`, `_create_status_bar_widgets`, `_build_status_bar_tooltip`) — `RealtimeModeIconMixin` and the heater/magnet overrides keep working untouched. New overridable trait `status_bar_plugin_id` (default: pane id `"<pkg>.dock_pane"` → `"<pkg>.plugin"`).

- [ ] **Step 1: Delete the placement constants and spacer import**

Remove from `base_dock_pane.py`:
- the line `from microdrop_utils.pyside_helpers import horizontal_spacer_widget`
- the module constants block:

```python
#: Position in the status bar at which every pane widget is inserted.
STATUS_BAR_INSERT_INDEX = 2

#: Width (px) of the spacer inserted alongside each status-bar widget.
STATUS_BAR_SPACER_WIDTH = 10
```

Change the traits import to include `Str`:

```python
from traits.api import Any, Instance, List, Str, observe
```

- [ ] **Step 2: Replace the tracking trait with contribution traits**

Replace (lines 121-124):

```python
    #: Every widget this pane inserted into the status bar (icons AND their
    #: spacers), tracked so destroy() can remove exactly what was added —
    #: required for runtime hot unload of the pane.
    _status_bar_inserted_widgets = List()
```

with:

```python
    #: Id of the Envisage plugin whose ``status_bar_icons`` contribution
    #: list this pane extends; "<pkg>.dock_pane" → "<pkg>.plugin" by
    #: convention (override for panes that don't follow it).
    status_bar_plugin_id = Str()

    #: The contribution plugin resolved at populate time, cached so
    #: teardown can withdraw contributions without touching the window.
    _contribution_plugin = Any(None)

    #: Widgets this pane contributed to the status bar, tracked so
    #: teardown withdraws exactly what was added — required for runtime
    #: hot unload of the pane.
    _contributed_status_bar_widgets = List()

    def _status_bar_plugin_id_default(self):
        return self.id.rsplit(".", 1)[0] + ".plugin"
```

- [ ] **Step 3: Rewrite `_populate_status_bar`**

Replace the whole method (keeping the decorator):

```python
    @observe("task:window:status_bar_manager")
    def _populate_status_bar(self, event):
        """Build the pane's status-bar widgets and contribute them to the
        status-bar extension point — the microdrop_status_bar plugin owns
        placement, spacing, and removal.

        Subclass overrides MUST re-apply the @observe decorator above —
        an undecorated override silently drops the observer registration."""
        if self._contributed_status_bar_widgets:
            return                      # already populated (observer + hot-mount)
        plugin = self.task.window.application.get_plugin(
            self.status_bar_plugin_id
        )
        if plugin is None:
            logger.warning(
                f"{self.id}: no plugin {self.status_bar_plugin_id!r} to carry "
                f"status-bar contributions; status-bar icons not shown"
            )
            return
        self.status_bar_icon = self._create_status_bar_icon()
        self._refresh_status_bar_tooltip()
        QApplication.styleHints().colorSchemeChanged.connect(
            self._refresh_status_bar_tooltip
        )
        widgets = self._create_status_bar_widgets()
        self._contribution_plugin = plugin
        self._contributed_status_bar_widgets = list(widgets)
        plugin.status_bar_icons.extend(widgets)
```

- [ ] **Step 4: Rewrite `_teardown_status_bar`**

Replace the whole method:

```python
    def _teardown_status_bar(self):
        """Withdraw this pane's status-bar contributions and signal hookups.

        Removing the widgets from the plugin's contribution list fires the
        extension-point event that makes the status-bar plugin take them
        out of the bar and delete them. Idempotent: widgets already gone
        from the list (e.g. the plugin was hot-unloaded first) are skipped.
        """
        if self._contributed_status_bar_widgets:
            try:
                QApplication.styleHints().colorSchemeChanged.disconnect(
                    self._refresh_status_bar_tooltip
                )
            except (RuntimeError, TypeError):
                pass                    # never connected / already gone
            contributed = self._contribution_plugin.status_bar_icons
            for widget in self._contributed_status_bar_widgets:
                if widget in contributed:
                    contributed.remove(widget)
            self._contributed_status_bar_widgets = []
            self._contribution_plugin = None
        self.status_bar_icon = None
```

- [ ] **Step 5: Syntax check**

Run: `python -c "import ast; ast.parse(open('template_status_and_controls/base_dock_pane.py').read())"`
Expected: no output (exit 0). Also grep to confirm nothing else references the deleted names:
`grep -rn "STATUS_BAR_INSERT_INDEX\|STATUS_BAR_SPACER_WIDTH\|_status_bar_inserted_widgets" --include="*.py" .`
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add template_status_and_controls/base_dock_pane.py
git commit -m "refactor: BaseStatusDockPane contributes status-bar icons via extension point"
```

---

### Task 4: Remove status-bar creation from `MicrodropTask` + stale-comment touch-up

**Files:**
- Modify: `microdrop_application/task.py`
- Modify: `microdrop_utils/pyface_helpers.py` (comments only)

**Interfaces:**
- Consumes: nothing new. StatusBarPlugin (Task 1) now creates the `StatusBarManager`; `device_viewer` and the panes react to the same `task:window:status_bar_manager` / `application:active_window` events regardless of who set the trait.

- [ ] **Step 1: Shrink `activated()`**

In `microdrop_application/task.py` replace the `activated` method with:

```python
    def activated(self):
        """Called when the task is activated."""
        logger.info("Microdrop task activated")
```

(The status-bar creation moved to the `microdrop_status_bar` plugin.) Delete the now-unused import:

```python
from microdrop_utils.pyface_helpers import StatusBarManager
```

Verify `StatusBarManager` has no other use in the file: `grep -n "StatusBarManager" microdrop_application/task.py` → no matches.

- [ ] **Step 2: Fix the stale cross-reference comments in `pyface_helpers.py`**

Replace the `STATUSBAR_FIRST_PERMANENT_INDEX` comment (lines 27-30):

```python
#: First permanent-widget slot. Indices 0/1 are the non-permanent persistent and
#: center labels, so permanent icons start at 2. Inserting here lands LEFT of
#: the microdrop_status_bar icon container, which is appended at the right end.
STATUSBAR_FIRST_PERMANENT_INDEX = 2
```

In `attach_gamepad_indicator`'s docstring, replace the sentence
"Mirrors the icon+spacer pattern used by template_status_and_controls so spacing stays uniform: insert the icon, then a leading spacer, both at the first permanent index — giving [spacer][joystick][…other icons, each with their own leading spacer]."
with:
"Insert the icon, then a leading spacer, both at the first permanent index — giving [spacer][joystick][microdrop_status_bar icon container]." (code unchanged).

- [ ] **Step 3: Commit**

```bash
git add microdrop_application/task.py microdrop_utils/pyface_helpers.py
git commit -m "refactor: move status-bar creation out of MicrodropTask into microdrop_status_bar"
```

---

### Task 5: Register `StatusBarPlugin`

**Files:**
- Modify: `examples/plugin_consts.py`

**Interfaces:**
- Consumes: `microdrop_status_bar.plugin.StatusBarPlugin` (Task 1).

- [ ] **Step 1: Import and list it**

In `examples/plugin_consts.py` add with the other plugin imports:

```python
from microdrop_status_bar.plugin import StatusBarPlugin
```

In `FRONTEND_PLUGINS`, insert directly after `TasksPlugin`:

```python
FRONTEND_PLUGINS = [
    MicrodropPlugin,
    TasksPlugin,
    StatusBarPlugin,
    ...
```

(Frontend-only: the backend application has no windows. Load order carries no service-priority concern here — the plugin offers no services — but early placement means the extension point exists before any contributor starts.)

- [ ] **Step 2: Commit**

```bash
git add examples/plugin_consts.py
git commit -m "feat: register StatusBarPlugin in frontend plugin list"
```

---

### Task 6: Manual verification (human)

No automated runs — hand this checklist to the user:

- [ ] Launch the app (`python examples/run_device_viewer_pluggable.py` with Redis up) — the DropBot status icon and realtime toggle appear right of the joystick icon, evenly spaced; "Free Mode" shows on the left.
- [ ] Hover the icons — tooltips render; switch OS theme — tooltip colors follow.
- [ ] Tools → Peripherals: enable the magnet group — its icon appears with the same spacing; disable — it disappears, remaining icons close ranks.
- [ ] Start/stop camera recording — the recording icon still pulses in its usual spot (device_viewer path untouched).
- [ ] Quit — no status-bar teardown errors in the log.
