# Plugin-management UX overhaul — unified Manage Plugins window (TraitsUI MVC)

**Date:** 2026-06-26
**Status:** Approved (design discussed + approved in conversation)
**Branch:** `feat/plugin_management` (Microdrop submodule)
**Builds on:** the plugins-as-conda-packages migration
(`docs/superpowers/specs/2026-06-26-plugin-conda-package-migration-design.md`).

## Problem & goal

The plugin UX is three separate Tools actions (Install / Uninstall / Manage Plugins), the install
gives no preview of what's being installed and no feedback during the (slow) `pixi add`, and the
Manage dialog lists every group as a flat checkbox. Unify this into **one** Manage Plugins window
with: a richer pre-install preview, a "please wait" loading state, and a per-plugin row showing the
plugin **version** and an **Enable + per-optional-group** checkbox model. Build the window with a
clean TraitsUI **Model / View / Controller** split.

## Decisions (locked)

- **One window:** Tools → **Manage Plugins…** replaces all three current actions.
- **Enable model:** a plugin's manifest marks certain groups **optional**; the row shows **Enable**
  + one checkbox per optional group. Checking Enable enables the plugin's core groups and
  auto-checks the optionals; an optional can be unchecked to run partial (e.g. UI-only, no backend).
- **Apply = live** runtime hot-load (no relaunch). **Install / Uninstall = relaunch** (so the dialog
  session ends; the list needn't live-refresh).
- **Preview** is read from the `.conda` archive (name/version/deps from `info/index.json`; groups +
  plugin classes from the bundled `microdrop_plugin.toml`).
- **Loading:** `pixi add`/`pixi remove` run on a worker thread behind a modal indeterminate
  "Please wait" dialog; completion marshals back to the GUI thread.
- **Architecture:** TraitsUI MVC — Qt-free `HasTraits` model (state + business logic), a TraitsUI
  `Controller` (glue), and a TraitsUI `View`. Aligns with the repo's existing MVC-separation
  convention (model mutated only on the GUI thread; no Qt in the model).

## Window layout (the View)

```
Manage Plugins
--------------------------------------------------
Installed plugins:
                          Enable   Backend
  Magnet        v1.0.0       [x]      [x]
  Acme Tools    v0.3.0       [ ]       -

  [ Install Plugin... ]      [ Uninstall v ]
              [ Apply ]   [ Close ]
```
- One row per installed plugin (manifest), with **name + version**.
- **Enable** = master checkbox; one extra checkbox per optional group (column label from the
  group's `toggle_label`, e.g. **Backend**). A plugin with no optional groups shows only Enable.
- **Apply** commits enable/disable as a live hot-load. **Install Plugin…** / **Uninstall ▾** launch
  their flows (which end in a relaunch). **Close** dismisses.

## Manifest schema change

`PluginGroupSpec` (`manifest.py`) gains two optional fields:
- `optional: bool = False` — the group is independently toggleable (shown as its own checkbox).
- `toggle_label: str = ""` — short column label for the optional checkbox (falls back to `label`).

`manifest_from_dict` reads them (defaults preserve every existing manifest). `PluginGroup`
(`group_manager.py`) gains matching `optional`/`toggle_label` traits, threaded through
`_add_manifest_groups`. Magnet's `peripheral_controller/microdrop_plugin.toml`: mark
`magnet_backend` with `optional = true`, `toggle_label = "Backend"`; `magnet_ui` stays core.

## Architecture — TraitsUI MVC

### Model — `plugin_management/manager_model.py` (Qt-free `HasTraits`)

Holds state + all business logic; no Qt, no dialogs, no threading.

- `OptionalGroupToggle(HasTraits)`: `group_name: Str`, `toggle_label: Str`, `on: Bool` — one per
  optional group (a `List(Instance(...))` binds to TraitsUI checkboxes cleanly, unlike a `Dict`).
- `PluginRow(HasTraits)`: `manifest_name`, `label`, `version`, `dist_name`, `bundled: Bool`,
  `core_groups: List(Str)`, `optionals: List(Instance(OptionalGroupToggle))`, `enabled: Bool`. An
  `@observe("enabled")` sets every `optionals[*].on` True when `enabled` flips True (the auto-check);
  when `enabled` is False the optionals are treated as off.
- `PluginManagerModel(HasTraits)`:
  - `manager` (the `IPluginGroupManager` service), `rows = List(Instance(PluginRow))`.
  - `_rows_default` / `refresh()` — build one `PluginRow` per manifest from `manager.groups`
    (grouped by `manifest_name`), seeding `enabled`/`optional_on` from each group's live `loaded`
    state, classifying groups by their `optional` flag, and recording version (`manifest`/group
    metadata) + `bundled` (`dist_name` == the app's dist).
  - `desired_state() -> dict[str, bool]` — per row: `enabled` off ⇒ all its groups False;
    `enabled` on ⇒ core groups True + each optional group per its `OptionalGroupToggle.on`.
  - `apply(task)` — `manager.apply(task, self.desired_state())` (live hot-load).
  - `installed_rows()` — rows that are not bundled (uninstallable), for the Uninstall picker.
  - `preview(conda_path) -> PluginPreview` — delegate to `package_installer.read_conda_preview`.
  - `do_install(conda_path) -> InstallResult` / `do_uninstall(name)` — delegate to
    `package_installer` (run by the controller on a worker thread; these only call subprocess/pixi,
    they never touch Qt or the model).

### View — `plugin_management/manager_view.py`

A function `manager_view(model) -> traitsui.View` building the layout from `model.rows`: a
programmatic `VGroup` of per-row `HGroup`s (name+version label, the `enabled` checkbox, and a
checkbox per optional group bound to `optional_on`), plus the action buttons. Buttons are TraitsUI
`Action`s (`Install Plugin…`, `Uninstall…`, `Apply`, `Close`) whose handlers live on the
controller. `kind="livemodal"`, resizable.

### Controller — `plugin_management/manager_controller.py` (TraitsUI `Controller`)

`PluginManagerController(Controller)` pairs the model with the view and owns the UI glue
(dialogs, threading, relaunch). It holds `task`/`application` for the service + relaunch.

- `Install`: file picker (`*.conda`) → `model.preview(path)` → **preview/consent dialog** (formatted
  name/version/deps/groups, HTML-escaped) → on consent, run `model.do_install(path)` on a worker
  thread behind the **wait dialog**; on success (GUI thread) show the relaunch Yes/No →
  `relaunch.relaunch_app(application)` on Yes.
- `Uninstall`: choose from `model.installed_rows()` (a small enum/list picker) → confirm → threaded
  `model.do_uninstall(name)` behind the wait dialog → relaunch Yes/No.
- `Apply`: `model.apply(self.task)` (no relaunch); refresh row state.
- All dialogs via `microdrop_application.dialogs.pyface_wrapper`. The worker→GUI hand-off uses
  `pyface.api.GUI.invoke_later` so the model/dialogs are only touched on the GUI thread.

### Loading helper — `microdrop_utils/threaded_progress.py` (Qt allowed; it's a helper)

`run_with_wait(callable, *, title, message, on_success, on_error)`: shows a modal indeterminate
pyface `ProgressDialog` (or a simple "please wait" modal), runs `callable` on a worker thread, and
on completion invokes `on_success(result)` / `on_error(exc)` back on the GUI thread via
`GUI.invoke_later`, closing the wait dialog. Used by the controller for install + uninstall.

## Pre-install preview — reading the `.conda`

`package_installer.read_conda_preview(conda_path) -> PluginPreview` (dataclass: `name`, `version`,
`depends: list[str]`, `manifest: PluginManifest | None`). It reads `info/index.json` (name, version,
`depends`) the same way `package_name_from_conda` already does (via `backports.zstd` + the info
member), and additionally extracts the package's `microdrop_plugin.toml` from the `.conda`'s
**pkg** member (the `pkg-*.tar.zst` payload), parsing it with `manifest_from_dict` to list the
groups + plugin classes. If the manifest can't be read, the preview still shows name/version/deps
(the consent dialog degrades gracefully).

## Data flow

```
Tools → Manage Plugins… → controller.edit_traits(view, livemodal) over PluginManagerModel
  rows: one per installed plugin (name+version, Enable + optional checkboxes seeded from live state)
  toggle Enable/optionals → Apply → model.desired_state() → manager.apply (live hot-load)
  Install Plugin… → pick .conda → model.preview → consent dialog → run_with_wait(model.do_install)
        → success → relaunch Yes/No → relaunch_app
  Uninstall ▾ → pick installed plugin → confirm → run_with_wait(model.do_uninstall) → relaunch Yes/No
```

## Error handling

- Install/uninstall failures surface (GUI thread) as an error dialog; `package_installer` already
  rolls back pyproject/lock on a failed install.
- A bad/unsigned `.conda` (consent declined, unreadable archive) aborts cleanly before any pixi call.
- Enabling a plugin whose deps aren't present yet (user deferred a relaunch) fails to load cleanly
  via the existing `_resolve_factories` import-abort backstop.
- The wait dialog is non-cancellable (a `pixi add` isn't safely interruptible); this is acceptable.

## Files

**New:** `plugin_management/manager_model.py`, `plugin_management/manager_view.py`,
`plugin_management/manager_controller.py`, `microdrop_utils/threaded_progress.py`.
**Edit:** `plugin_management/menus.py` (one `ManagePluginsAction` opening the controller; remove the
Install/Uninstall actions), `plugin_management/manifest.py` (+`optional`/`toggle_label`),
`plugin_management/group_manager.py` (`PluginGroup` fields; thread through `_add_manifest_groups`),
`plugin_management/package_installer.py` (`read_conda_preview` + the pkg-member extraction),
`peripheral_controller/microdrop_plugin.toml` (mark backend optional), `plugin_management/plugin.py`
(TASK_EXTENSIONS: contribute only the single Manage Plugins action).
**Remove:** `plugin_management/manage_dialog.py` and `plugin_management/uninstall_dialog.py`
(replaced by the MVC trio).

## Verification (no pytest)

`py_compile` + import smokes for the model/controller/view and `read_conda_preview` (against the
demo `.conda`); a headless model smoke (`desired_state()` over a magnet-shaped fixture: Enable on →
ui+backend; uncheck Backend → ui only; Enable off → none); and manual GUI end-to-end: open Manage
Plugins, see magnet with Enable + Backend and a version; toggle + Apply hot-loads correctly;
Install a demo `.conda` shows the preview + wait dialog + relaunch; Uninstall likewise.

## Out of scope

Multi-select bulk actions; a true split-button dropdown (a simple picker suffices for Uninstall);
plugin search/filtering; reordering; the per-user-channel fix (tracked separately).
