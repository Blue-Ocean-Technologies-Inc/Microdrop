# Envisage / Traits / TraitsUI — Framework Guide for MicroDrop

This guide explains the **Enthought application stack** that MicroDrop is built on,
and how this codebase actually uses it. It is balanced: each section gives the
framework concept, then **"In MicroDrop"** — real files cited as `path:line`
(paths relative to `microdrop-py/src/` unless noted).

It is a *framework* guide. It deliberately does **not** restate:
- the enforced coding rules → see the `microdrop-conventions` skill
  (`microdrop-py/.claude/skills/microdrop-conventions/SKILL.md`),
- the pub/sub topic map → see [`MESSAGES.md`](MESSAGES.md),
- the Dramatiq API notes → see [`DRAMATIQ_DOCS.md`](DRAMATIQ_DOCS.md),
- the high-level three-layer architecture → see `microdrop-py/CLAUDE.md`.

---

## 1. Orientation

### The stack

```
        ┌─────────────────────────────────────────────────────────┐
        │  envisage          plugin application: Plugins, extension│
        │                    points, service registry, Tasks GUI   │
        ├─────────────────────────────────────────────────────────┤
        │  apptools          persisted preferences (PreferencesHelper)
        │  pyface / traitsui toolkit-independent UI over Qt/wx;    │
        │                    Tasks framework; declarative Views    │
        ├─────────────────────────────────────────────────────────┤
        │  traits            typed attributes + change notification │
        │                    (the foundation everything sits on)   │
        └─────────────────────────────────────────────────────────┘
                        Qt binding: PySide6
```

Mental model, bottom-up: **traits** gives you typed, observable attributes.
**traitsui** turns a traits object into a GUI without you touching Qt. **pyface**
is the toolkit-abstraction layer traitsui renders through (and provides the Tasks
windowing framework). **apptools** adds persisted preferences. **envisage** ties it
all together into a plugin application where every feature is a `Plugin` that
contributes to **extension points** and the **service registry**.

### Pinned versions

Source of truth: `microdrop-py/pyproject.toml` `[tool.pixi.dependencies]`
(conda-forge), confirmed in `pixi.lock` and the installed `.dist-info`.

| Package    | Constraint        | Installed |
|------------|-------------------|-----------|
| `traits`   | `>=7.0.2,<8`      | 7.1.0     |
| `traitsui` | `>=8.0.0,<9`      | 8.0.0     |
| `pyface`   | `>=8.0.0,<9`      | 8.0.0     |
| `apptools` | `>=5.3.1,<6`      | 5.3.1     |
| `envisage` | `>=7.0.4,<8`      | 7.0.4     |

Python 3.13, Qt binding `pyside6`. `encore` is **not** a dependency.

> **traitsui 8 note:** the Qt backend module is `traitsui.qt` (the old
> `traitsui.qt4` alias is gone). Custom editors here import from
> `traitsui.qt.editor`.

### Where to read the library source

Context7 has TraitsUI docs (`/enthought/traitsui`) but **not** traits or envisage.
For those, the authoritative reference is the installed package on disk:

```
microdrop-py/.pixi/envs/default/Lib/site-packages/{traits,traitsui,pyface,apptools,envisage}/
```

---

## 2. Traits — the foundation

### Concept

A `HasTraits` class declares **typed, class-level attributes** ("traits"). Traits
validate on assignment, supply defaults, and emit change notifications. Common
trait types used here: `Int Str Bool Float Enum Instance List Dict Any Property
Event Range Directory File Color Button UUID DelegatesTo`.

Key idioms:
- **Defaults via `_<name>_default(self)`** — lazy, computed once on first access.
- **`traits_init(self)` instead of `__init__`** — runs after traits are set up
  (the conventions skill mandates this for stateful classes).
- **`Property(observe=...)` / `depends_on=`** — a derived trait with a
  `_get_<name>` getter (and optional `_set_<name>`), recomputed/notified when its
  dependencies change.
- **`Instance("ClassName", ())`** — `()` means "default-construct one"; a string
  class name allows self-reference.
- **`DelegatesTo("child", prefix=...)`** — mirror a nested trait at the top level
  (needed because traitsui `enabled_when` doesn't re-evaluate deep paths reliably).

### Notification model — `@observe`

`@observe` is the **modern, mandated** notification mechanism (legacy
`on_trait_change` survives only for one special case, see §5). Path syntax:

| Pattern                         | Meaning                                            |
|---------------------------------|----------------------------------------------------|
| `@observe("mode")`              | trait changed; handler gets `event.new/old/name`   |
| `@observe("a.b.items")`         | extended path; `.items` fires on list add/remove   |
| `@observe("cam:transformation")`| `:` = **non-propagating** (only the final trait)   |
| `@observe("alpha_map.items.[alpha, visible]")` | multi-attr on list items            |

Other handler forms: `Button` triggers `_<name>_fired`; traitsui `Controller`s use
`_<name>_changed` / `<name>_setattr`.

### In MicroDrop

**Textbook pure model** — `pluggable_protocol_tree/models/protocol_status.py:19`.
A Qt-free, thread-free, unit-testable `HasTraits` state model; every timing method
takes `now` so a fake clock can drive it in tests. Clocks default-constructed via
`Instance(ScopeStopwatch, ())`. This is the canonical example of the MVC
"model is plain traits" rule.

**Rich composed model** — `device_viewer/models/main_model.py:29`
(`@provides(IDeviceViewMainModel)`):
- composition with `Instance` (`routes`, `electrodes`, `calibration`),
- `mode = Enum(...)` (`:71`) with `mode_name = Property(Str, observe="mode")` (`:75`),
- derived capacitance via `Property(Float, depends_on="calibration.last_capacitance")` (`:79`),
- `DelegatesTo("routes", prefix="commit_enabled")` (`:47`) to surface a nested
  trait for `enabled_when`,
- `Event`, `UUID`, `List`, `Int` traits (`:93-109`),
- and rich `@observe` handlers further down (mode changes, nested route/electrode
  list-item paths, non-propagating `camera_perspective:transformation`).

**`consts.py`-as-trait-name idiom** — constants double as trait names in observe
paths, e.g. `device_viewer/models/calibration.py` does `@observe(LIQUID_CAPACITANCE_KEY)`.

**Self-referential + runtime-built classes** — `pluggable_protocol_tree/models/row.py`:
`parent = Instance("BaseRow")`, a `Property(Tuple, observe="parent.path, ...")`, and
`build_row_type()` which uses `type(...)` to mint a `HasTraits` subclass with one
trait per active protocol column.

**Range-bounds gotcha** — `traits` `Range` bounds are fixed at *class-definition*
time. `manual_controls/MVC.py:130` works around it with a
`_make_manual_control_model()` factory that reads preferences first and builds the
class inside the function (`ManualControlModel = _make_manual_control_model()` at
`:159`); runtime bound changes mutate `trait('voltage').trait_type._low/_high`.

---

## 3. Pyface + apptools — toolkit abstraction & persisted config

### Concept

**pyface** wraps the native toolkit (here PySide6) behind toolkit-independent
classes, and provides the **Tasks** windowing framework:

- `Task` — a workspace (menus, layout) inside a `TaskWindow`.
- `DockPane` / `TaskPane` — dockable panels.
- `TaskExtension` + `SchemaAddition` — how *other* plugins inject dock panes and
  menu items into a task they don't own.

**apptools** provides persisted preferences: a `PreferencesHelper` subclass binds
traits to a `preferences_path` node; values round-trip to disk. A **trailing
underscore** on a trait name (`capture_prompt_`) marks it *not persisted*.

### In MicroDrop

**Styled dialogs that keep the pyface contract** —
`microdrop_application/dialogs/pyface_wrapper.py`. It re-exports pyface's dialog API
(`confirm` at `:127`, `information` `:188`, `warning` `:273`, `error` `:332`, plus
`YES/NO/OK/CANCEL`) but renders the app's own Qt `BaseMessageDialog`. **Callers
compare results against `YES`/`NO`/`CANCEL` directly** — do not mint parallel
decision constants (conventions skill).

**Pyface widgets extended with traits** — `microdrop_utils/pyface_helpers.py`:
`StatusBarManager` subclasses pyface's status-bar manager and adds
`center_message = Str()` with an `@observe` handler driving the centered
Qt label. `microdrop_utils/dramatiq_traits_helpers.py` subclasses
`pyface.tasks.action.TaskWindowAction`.

**Preferences** — `microdrop_application/preferences.py` and
`device_viewer/preferences.py`: `PreferencesHelper` subclasses pairing
`Range/Directory/File/Dict/Color/Button` traits with a traitsui `View`, wired into
the GUI via `PreferencesPane` / `PreferencesCategory` (see §5).

---

## 4. TraitsUI — declarative UI

### Concept

Describe *what* to show, not *how* to lay out widgets:

- `View` — top-level container; `kind` = `live`/`modal`/`nonmodal`/`panel`.
- `Item` / `UItem` (unlabeled) — bind one trait; `style` = `simple`/`custom`/
  `readonly`/`text`.
- `Group` / `HGroup` / `VGroup` / `VGrid` / `Spring` — layout.
- `enabled_when` / `visible_when` — string expressions over the object's traits.
- **Editors** — each trait type has a default editor; override with
  `editor=SomeEditor(...)`.
- **`Handler` / `Controller`** — non-visual glue (actions, validation, debounce).
  This repo uses `Controller`/`Handler`, **not** `ModelView`.
- `edit_traits()` embeds a view into a Qt layout; `configure_traits()` opens a
  standalone window (used only in `__main__` demo blocks here).
- **Custom editor contract**: subclass `traitsui.qt.editor.Editor` +
  `BasicEditorFactory`, implementing `init / update_object / update_editor /
  dispose`, guarding Qt signals with `blockSignals` to avoid feedback loops.

### In MicroDrop

TraitsUI is used **selectively** — sidebar status panels, preference panes, and
table grids — while heavy interactive widgets are hand-built PySide6.

**Sidebar panel** — `dropbot_status_and_controls/view.py:5`: `VGrid`/`HGroup` of
`Item`/`UItem` with `enabled_when="free_mode and not protocol_running and not halted"`
(`:36`) and `visible_when="show_dielectric_info"` (`:45`), using custom editors
(`StatusIconEditorFactory`, `HoverScrollEnumEditor`).

**Table editor + handler** — `device_viewer/views/alpha_view/alpha_table.py:9`:
a `TableEditor` with custom `VisibleColumn`/`ObjectColumn`/`RangeColumn` and a
context `Menu`/`Action`; `AlphaTableHandler(SafeCancelTableHandler)` (`:37`)
implements the `reset_defaults` action. The view is embedded with `edit_traits`
(`:82`).

**The custom-editor library** — `microdrop_utils/traitsui_qt_helpers.py` is the
biggest TraitsUI investment and the sanctioned place where Traits meets Qt directly:
`ObjectColumn` (`:40`), `RangeColumn` (`:97`), `SteppedSpinEditor` (`:193`),
`DictFloatTableEditor` (`:396`), `SafeCancelTableHandler` (`:422`),
`StatusIconEditor` (`:447`), `HoverScrollEnumEditor` (`:522`).

**MVC trio in one file** — `manual_controls/MVC.py`: model factory (`:130`),
`ManualControlView` (`:162`), and a `Controller` with `@observe("model:...")`
handlers and debounced setattr. `configure_traits` appears only in its `__main__`
demo.

---

## 5. Envisage — the plugin application

### Concept

Everything is a **`Plugin`** (has `id`, `name`, lifecycle `start()`/`stop()`).
Plugins are handed to an **`Application`** which starts them in order.

Two wiring mechanisms:

1. **Extension points** — a producer/consumer contract.
   - *Declare*: `ExtensionPoint(List(...), id=SOME_ID)` on the owning plugin.
   - *Contribute*: any plugin adds `List(..., contributes_to=SOME_ID)`.
   - Envisage aggregates all contributions per id. To react to contributions at
     runtime, the owner must opt in with `self.connect_extension_point_traits()`
     in `start()` (envisage never calls it for you).

2. **Service registry** — dependency injection.
   - *Offer*: `ServiceOffer(protocol=IFace, factory=...)` contributed to
     `SERVICE_OFFERS`.
   - *Consume*: `application.get_service(IFace)` (first match) or
     `get_services(IFace)` (all), with optional `query="expr"` filtering.

Built-in envisage/Tasks extension points the GUI uses: `TASKS`, `TASK_EXTENSIONS`,
`PREFERENCES`, `PREFERENCES_PANES`, `PREFERENCES_CATEGORIES`.

`Application` (headless) vs `TasksApplication` (GUI). **Load order matters**: the
plugin listed first starts first and *wins* `get_service` lookups.

Interfaces are plain `traits.api.Interface` subclasses in `interfaces/i_*.py`,
implemented via `@provides(IFace)`.

### In MicroDrop

**Bootstrap** — `examples/run_device_viewer_pluggable.py:40` `main()`:
instantiate plugins (`:59`), build the app `application(plugins=plugin_instances)`
(`:68`), `app.run()` (`:75`). The app class is `MicrodropApplication`
(`microdrop_application/application.py:66`, a `TasksApplication`) for the GUI, or
`MicrodropBackendApplication` (`microdrop_application/backend_application.py:25`, a
plain `Application`) headless.

**Plugin lists = the manifest** — `examples/plugin_consts.py`. There is no
setuptools entry-point manifest; plugins are listed in ordered Python lists:
`REQUIRED_PLUGINS` (`:118` — `CorePlugin`, `MessageRouterPlugin`, `LoggerPlugin`),
`FRONTEND_PLUGINS` (`:62`, includes `TasksPlugin`), `BACKEND_PLUGINS` (`:90`), plus
device/mock variants. Run scripts compose these by CLI flag.

**Representative plugin** — `dropbot_controller/plugin.py:24`:
- `id = PKG + '.plugin'` (`PKG` from `consts.py`),
- `service_offers = List(contributes_to=SERVICE_OFFERS)` (`:29`) with
  `_service_offers_default` (`:34`) returning `ServiceOffer(protocol=IFace,
  factory=...)`,
- `actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)`
  (`:32`),
- **service-mixin composition** in `start()` (`:76`): pull *all* matching services
  and build a class from them —
  ```python
  services = self.application.get_services(IDropbotControlMixinService) + [DropbotControllerBase]
  class DropbotController(*services): pass
  ```
  (mirrored in `opendrop_controller` and `peripheral_controller`).

**The extension-point hub** — `message_router/plugin.py`:
- declares `ACTOR_TOPIC_ROUTES` via `ExtensionPoint(List(Dict(Str, List)), id=...)`
  (`:26`); every other plugin contributes its `ACTOR_TOPIC_DICT`,
- `start()` calls `self.connect_extension_point_traits()` (`:43`) to wire runtime
  changes,
- **dual-handler nuance** (`:77-102`): contribution add/remove arrives as a
  synthetic `actor_topic_routing_items` event. `observe()` *rejects* that unknown
  name, so the handler must bind it with legacy
  `@on_trait_change("actor_topic_routing_items")` (`:77`) — this is the one place
  `on_trait_change` is still required. A separate `@observe("actor_topic_routing")`
  (`:93`) covers wholesale replacement. (Note: envisage wires *who subscribes to
  what*; the actual messages then flow over Dramatiq/Redis, not envisage.)

**Custom extension points** — `pluggable_protocol_tree/plugin.py`:
`PROTOCOL_COLUMNS` (`:63`, typed `List(Either(IColumn, ICompoundColumn))`) and
`PROTOCOL_QUICK_ACTIONS` (`:75`). Contributors are the `*_protocol_controls`
plugins (`dropbot_protocol_controls`, `peripheral_protocol_controls`,
`video_protocol_controls`, `volume_threshold_protocol_controls`) and
`protocol_quick_action_tools`.

**Built-in extension points** — `TASKS` (one `TaskFactory` from
`microdrop_application`), `TASK_EXTENSIONS` (device_viewer, manual_controls,
logger_ui, … each contributing dock panes + menu `SchemaAddition`s), and
`PREFERENCES{,_PANES,_CATEGORIES}` (~8 UI plugins). `microdrop_application`'s
custom preferences-dialog service even overrides an envisage built-in by offering a
service under a dotted-string protocol.

---

## 6. How it all fits — the synthesis

```
 run_device_viewer_pluggable.py
        │  picks ordered plugin lists from plugin_consts.py  (load order = priority)
        ▼
 Application(plugins=[...]).run()        ── Microdrop{,Backend}Application
        │
        │  envisage aggregates, per extension-point id, every
        │  List(contributes_to=ID) across all loaded plugins
        ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ EXTENSION POINTS                    SERVICE REGISTRY               │
 │  ACTOR_TOPIC_ROUTES (router)         SERVICE_OFFERS                │
 │   ◀ every plugin's ACTOR_TOPIC_DICT   ServiceOffer(protocol,factory)│
 │  PROTOCOL_COLUMNS / _QUICK_ACTIONS    consumed via get_services()  │
 │   ◀ *_protocol_controls plugins       → class X(*services) mixin   │
 │  TASKS / TASK_EXTENSIONS / PREFERENCES_*  → Tasks GUI assembled    │
 └──────────────────────────────────────────────────────────────────┘
        │
        ▼
 envisage wires WHO subscribes to WHAT.  Actual inter-plugin messages
 then flow over Dramatiq/Redis  ──▶  see MESSAGES.md / DRAMATIQ_DOCS.md
```

The throughline: **traits** models hold state and notify; **traitsui/pyface**
render a slice of them; **apptools** persists config; **envisage** composes plugins
via extension points + services; and **Dramatiq/Redis** carries the runtime
messages between the decoupled plugins. The `microdrop-conventions` skill is the
rulebook that keeps each layer clean (Qt-free models, `@observe`, `@provides`
interfaces, plugin decoupling).

---

## 7. Reading map — go deeper

**Best repo files to read first**
- Model / traits: `pluggable_protocol_tree/models/protocol_status.py`,
  `device_viewer/models/main_model.py`, `pluggable_protocol_tree/models/row.py`.
- TraitsUI: `dropbot_status_and_controls/view.py`,
  `device_viewer/views/alpha_view/alpha_table.py`,
  `microdrop_utils/traitsui_qt_helpers.py`, `manual_controls/MVC.py`.
- Pyface/apptools: `microdrop_application/dialogs/pyface_wrapper.py`,
  `microdrop_utils/pyface_helpers.py`, `microdrop_application/preferences.py`,
  `device_viewer/preferences.py`.
- Envisage: `examples/run_device_viewer_pluggable.py`, `examples/plugin_consts.py`,
  `dropbot_controller/plugin.py`, `message_router/plugin.py`,
  `pluggable_protocol_tree/plugin.py`, and the `examples/toy_plugins/` tutorial tree.

**Installed library source**
`microdrop-py/.pixi/envs/default/Lib/site-packages/{traits,traitsui,pyface,apptools,envisage}/`

**Official docs**
- TraitsUI — https://docs.enthought.com/traitsui/ (context7: `/enthought/traitsui`)
- Traits — https://docs.enthought.com/traits/
- Pyface — https://docs.enthought.com/pyface/
- Envisage — https://docs.enthought.com/envisage/
- apptools — https://docs.enthought.com/apptools/

**Related in-repo docs**
- `microdrop-py/CLAUDE.md` — architecture & messaging overview.
- `microdrop-py/.claude/skills/microdrop-conventions/SKILL.md` — enforced rules.
- [`MESSAGES.md`](MESSAGES.md), [`DRAMATIQ_DOCS.md`](DRAMATIQ_DOCS.md),
  [`README.md`](README.md).
