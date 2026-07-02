# Status-Pane Template Refactor — Design

**Date:** 2026-07-02
**Scope:** `template_status_and_controls/base_dock_pane.py` and its four
subclasses (`dropbot_status_and_controls`, `mock_dropbot_status`,
`opendrop_status_and_controls`, `heater_controls_ui`).
**Goal:** make `BaseStatusDockPane` a genuine device-neutral template so
subclasses only ever ADD behavior — never stub inherited behavior out — and
kill the shared class-level model/controller wiring. Zero visible behavior
change for any device.

## Problems

1. **DropBot code in the "generic" base.** `_setup_statusbar_icon` builds a
   DropBot drop icon (`ICON_DROP_EC`) plus a realtime-mode toggle publishing
   `SET_REALTIME_MODE` (imported from `dropbot_controller.consts`), and the
   base imports colors from `dropbot_status_and_controls.consts` (dead
   imports). A template package depending on a concrete device plugin is
   backwards layering.
2. **Subclasses subtract instead of add.** The heater pane overrides
   `_setup_statusbar_icon` wholesale and stubs
   `_enable_realtime_icon_based_on_modes` / `_sync_realtime_icon` as `pass`
   no-ops because the base observers reference a `realtime_mode_icon` it
   never creates.
3. **Duplicate tooltip builders.** `_build_status_icon_tooltip` (base) and
   `_build_heater_status_tooltip` (heater) render the same HTML skeleton.
4. **Shared class-level wiring.** Every subclass repeats
   `model = X(); view = V; controller = C(model); view.handler = controller`,
   instantiating shared mutable objects at class-definition time and mutating
   the shared `View` — the very bug the base's docstring says it exists to
   avoid. `status_bar_icon` / `realtime_mode_icon` / `message_handler` /
   `_dialog_signals` are plain instance variables (violates the always-Traits
   directive), forcing `hasattr`/`getattr` guards.

## Design

### 1. `base_dock_pane.py` — device-neutral template

- **Per-instance wiring.** `traits_init` calls three factory hooks —
  `_create_model()`, `_create_controller()`, `_create_message_handler()`
  (subclass must implement) — then `_setup_extras()` (optional, default
  no-op). An overridden `create_contents` passes `handler=self.controller`
  to `edit_traits`, so `view.handler` is never assigned; subclasses keep the
  class-level `view = SomeView` declaration (TraitsUI resolves it by name).
- **Traits, not instance variables:** `controller = Instance(Handler)`,
  `message_handler = Instance(IMessageHandler)`, `status_bar_icon = Any(None)`.
- **Generic status bar.** The `task:window:status_bar_manager` observer
  (`_populate_status_bar`) builds `self.status_bar_icon` via the
  `_create_status_bar_icon()` factory, applies the tooltip, wires
  `colorSchemeChanged` → `_refresh_status_bar_tooltip`, and inserts each
  widget from `_create_status_bar_widgets()` (plus a spacer) at the same
  index/order as today. Customization points:
  - `status_bar_icon_glyph` — class attr, the icon-font glyph.
  - `_create_status_bar_icon()` — default: plain `QLabel` (heater returns a
    `ClickableLabel` wired to a connection scan).
  - `_create_status_bar_widgets()` — default `[self.status_bar_icon]`;
    extenders return `super() + [...]`.
  - `_build_status_bar_tooltip()` — default: the 4 standard device states.
- **Shared helpers** (module level): `status_bar_icon_font()` and
  `build_status_icon_tooltip(title, states, hint=None)` where `states` is an
  iterable of `(color, label)` pairs — replaces both HTML builders.
  Module-top constants: `STATUS_BAR_INSERT_INDEX = 2`,
  `STATUS_BAR_SPACER_WIDTH = 10`.
- **No DropBot imports.** `SET_REALTIME_MODE`, `ICON_DROP_EC`, and the
  `dropbot_status_and_controls.consts` colors all leave the base.

### 2. New `realtime_mode_icon_mixin.py`

`RealtimeModeIconMixin(HasTraits)` — opt-in realtime toggle for the status
bar. Must be mixed in BEFORE `BaseStatusDockPane`. Contains:
- `realtime_mode_icon = Any(None)` trait.
- `_create_status_bar_widgets()` → `super() + [realtime icon]`, plus the
  initial enable/disable check.
- The three observers (`model.connected`/`model.protocol_running` enable
  check, `model.realtime_mode` sync), each None-guarded.
- Styles/tooltips as module-top constants. Imports only the
  `SET_REALTIME_MODE` topic constant (pub/sub contract — allowed).

### 3. Subclasses

- **dropbot / mock / opendrop:** `class X(RealtimeModeIconMixin,
  BaseStatusDockPane)`, `status_bar_icon_glyph = ICON_DROP_EC`, wiring moved
  into the three factories. Dropbot's `_dialog_signals`/`dialog_view` become
  `Instance` traits. Behavior identical to today.
- **heater:** no mixin. `status_bar_icon_glyph = ICON_MODE_HEAT`; overrides
  `_create_status_bar_icon` (ClickableLabel + scan-on-click),
  `_build_status_bar_tooltip` (3 states + searching hint), and
  `_populate_status_bar` (super() + initial search affordance).
  DELETED: `_setup_statusbar_icon` copy, `_refresh_status_tooltip`,
  `_build_heater_status_tooltip`, the `_setup_extras` stub, and the two
  `pass` no-op overrides.

## Error handling / risks

- Observer methods stay None-guarded so events arriving before the status
  bar exists are no-ops (same tolerance as today's `hasattr` guards).
- `RealtimeModeIconMixin` is never instantiated standalone, so its
  `model.*` observer patterns bind only in composed pane classes.
- No external consumers reach into these panes' class-level
  `model`/`controller` (verified by search), so moving wiring to instances
  is safe. The `__main__` demo blocks build their objects manually and are
  unaffected.

## Verification

Import smoke of all five modules in the pixi env (offscreen Qt); manual app
run by the user (no pytest per project preference).
