# Plugin install from the remote channel — design

**Date:** 2026-06-29
**Status:** Approved (brainstorming)
**Area:** `plugin_management/`

## Problem

Today, installing a plugin means picking a local built `.conda` file from a file
dialog (`PluginManagerHandler.install_plugin` → `file_dialog` →
`package_installer.read_conda_preview` / `install_conda_file`). Users should not
have to obtain and locate files manually.

Instead, the available plugins live in a hosted conda channel:

```
https://prefix.dev/microdrop-plugins
```

`pixi search "*" -c https://prefix.dev/microdrop-plugins --json` lists every
package in that channel with full metadata. The install flow should browse that
list, show details on demand, and install the chosen package directly from the
channel.

## Goals

- Replace the local-file install path with a **Browse Plugins** dialog listing
  the channel's packages.
- Table shows **Name / Version**; a **More details** button shows the selected
  row's full metadata in a read-only panel in the same dialog.
- **Fetch fresh** on open, **cache to app-data**, render from the cached file;
  fall back to the last cached file when offline.
- Keep the existing third-party-code **consent** confirm before installing.
- Install the selected package from the channel via `pixi add`.
- Remove the now-dead local-`.conda` code.

## Non-goals

- No multi-select / batch install (one package at a time).
- No version picker — install the latest the channel offers (what `pixi add`
  resolves). The table shows the latest version per package.
- No background/periodic refresh; fetch happens when the dialog opens.
- No plugin-group breakdown in the consent dialog (groups live inside the
  `.conda`, not in the search metadata; not downloaded pre-install).

## The data: `pixi search ... --json`

`--json` cannot be combined with `--limit`/`--limit-packages`; the JSON dump
already includes every package. Output is keyed by subdir; pixi prints a
deprecation warning and a `Using channels:` line to stderr, so stdout starts at
the `{`. Example (one package):

```json
{
  "noarch": [
    {
      "build": "pyh4616a5c_0",
      "build_number": 0,
      "depends": ["scipy >=1.10", "python >=3.11", "python *"],
      "md5": "537115f431813e38d5599fe2df20b178",
      "name": "scipy_analysis",
      "noarch": "python",
      "run_exports": {},
      "sha256": "f4aa51f8f1d696e91c5d8155f3f75985b7d24d1eac8bbeef910884f04365e7c2",
      "size": 5485,
      "subdir": "noarch",
      "timestamp": 1782507668846,
      "version": "0.1.0",
      "fn": "scipy_analysis-0.1.0-pyh4616a5c_0.conda",
      "url": "https://prefix.dev/microdrop-plugins/noarch/scipy_analysis-0.1.0-pyh4616a5c_0.conda",
      "channel": "https://prefix.dev/microdrop-plugins/"
    }
  ]
}
```

### Detail-block field mapping

Rendered for the selected row (matching the requested layout):

```
scipy_analysis-0.1.0-pyh4616a5c_0
---------------------------------

Name                scipy_analysis        <- name
Version             0.1.0                 <- version
Build               pyh4616a5c_0          <- build
Size                5.36 KiB              <- size (bytes -> KiB)
Timestamp           2026-06-26 21:01:08 UTC  <- timestamp (ms epoch -> UTC)
Subdir              noarch                <- subdir
NoArch              python                <- noarch
File Name           scipy_analysis-0.1.0-pyh4616a5c_0.conda  <- fn
URL                 https://prefix.dev/microdrop-plugins/noarch/scipy_analysis-0.1.0-pyh4616a5c_0.conda  <- url
MD5                 537115f431813e38d5599fe2df20b178  <- md5
SHA256              f4aa51f8f1d696e91c5d8155f3f75985b7d24d1eac8bbeef910884f04365e7c2  <- sha256

Dependencies:
 - scipy >=1.10        <- depends[]
 - python >=3.11
 - python *
```

- **Size**: `size` bytes → `f"{size/1024:.2f} KiB"` (binary KiB, matching pixi).
- **Timestamp**: `timestamp` is ms since epoch → format UTC as
  `YYYY-MM-DD HH:MM:SS UTC`.
- Header line is `fn` without the `.conda` suffix.
- Missing/empty fields render blank rather than raising.

## Architecture

Mirrors the existing Manage-Plugins MVC split: Qt-free `HasTraits` model,
TraitsUI view, `Handler` controller. The blocking subprocess work runs on a
worker thread behind the modal progress dialog (`run_with_wait`).

### `consts.py`

```python
PLUGIN_CHANNEL_URL = "https://prefix.dev/microdrop-plugins"
```

### `paths.py`

```python
def plugin_index_file() -> Path:
    """App-data cache file holding the last fetched channel package list (JSON)."""
    # ETSConfig.application_home / "plugin_index.json"
```

### `package_installer.py` (changes)

Add:

- `search_channel(channel_url, *, cwd=None) -> list[dict]`
  - Runs `pixi search "*" -c <channel_url> --json` (via the existing `_run`).
  - Locates the JSON in stdout (first `{`), parses, flattens the per-subdir
    lists into one list of package dicts.
  - Writes the parsed list to `paths.plugin_index_file()` (the app-data cache).
  - Returns the list. Raises `InstallError` on subprocess/parse failure.
- `read_cached_index() -> list[dict]`
  - Reads `paths.plugin_index_file()`; returns `[]` if missing/unreadable.
- `install_from_channel(name, channel_url, *, confirm=None, cwd=None) -> InstallResult`
  - Snapshot `pyproject.toml` + `pixi.lock` (existing `_snapshot`).
  - `_ensure_channel_registered(channel_url, cwd)` (existing helper; tolerate
    "already" registered). Note: the helper currently takes a directory and
    calls `.as_uri()`; generalize it to accept a URL string directly (a remote
    URL is already a URI).
  - `_run(["add", name], cwd=cwd)` — solver resolves name + deps from the
    registered channels.
  - Roll back (`_restore`) on any failure. Returns
    `InstallResult(name=name, requires_relaunch=True)`.

Remove (dead local-file path):

- `read_conda_preview`, `install_conda_file`, `package_name_from_conda`,
  `_conda_manifest`, `_zst_tar`, `_index_channel`, `_index_channel_safe`,
  and the `zstd`/`zipfile`/`tarfile`/`io` imports they used.
- `uninstall_package` simplifies to `pixi remove <name>` only (no local channel
  `.conda` cleanup, since nothing is copied locally anymore).
- `paths.plugin_channel_dir()` becomes unused → remove it.
- `InstallCancelled` / `PluginPreview` removed if unused after the above.

### `browse_model.py` (new, Qt-free)

```python
class AvailablePackage(HasTraits):
    name = Str()
    version = Str()
    raw = Dict()           # the full package dict, for the details panel

class BrowsePluginsModel(HasTraits):
    channel_url = Str(PLUGIN_CHANNEL_URL)
    packages = List(Instance(AvailablePackage))
    selected = Instance(AvailablePackage)
    details_text = Str()
    stale = Bool(False)    # True when showing the cached list after a fetch failure

    def fetch(self):
        # try package_installer.search_channel(); on InstallError fall back to
        # read_cached_index() and set stale=True. Build AvailablePackage rows
        # (latest version per name).

    def format_details(self, pkg) -> str:
        # render the detail block from pkg.raw (size/timestamp/deps formatting)

    def do_install(self, name):
        return package_installer.install_from_channel(name, self.channel_url)
```

Helpers for size/timestamp formatting live with the model (or in
`microdrop_utils` if reused elsewhere — not currently).

### `browse_view.py` (new, TraitsUI)

- `TableEditor` with `ObjectColumn(name)`, `ObjectColumn(version)` (from
  `microdrop_utils.traitsui_qt_helpers`, so text color follows the theme),
  `selection_mode="row"`, `selected="selected"`, read-only.
- Read-only multi-line text panel bound to `details_text` (monospace).
- Buttons: **More details** (`show_details`), **Install** (`install_selected`),
  **Close**. `kind="livemodal"`, resizable.

### `browse_controller.py` (new, `SafeCancelTableHandler` subclass)

- `init(info)` — kick off `fetch()` on a worker via `run_with_wait`, then
  populate the model on success; if `stale`, surface the offline note. (Calls
  `super().init(info)` for the Escape-deselect behavior.)
- `show_details(info)` — if a row is selected, set
  `model.details_text = model.format_details(model.selected)`; else prompt to
  select a row.
- `install_selected(info)` — require a selection; show the existing consent
  confirm (name / version / deps / unverified-code warning); on YES run
  `model.do_install(name)` via `run_with_wait`; on success show the relaunch
  prompt (reuse the existing `_after_change` relaunch flow).
- `do_close(info)` — `info.ui.dispose()`.

### `manager_controller.py` (change)

`install_plugin(info)` no longer opens a file dialog. It opens the Browse
Plugins dialog:

```python
def install_plugin(self, info):
    model = BrowsePluginsModel()
    model.edit_traits(view=browse_view, handler=BrowsePluginsHandler(task=self.task),
                      kind="livemodal")
```

The relaunch-after-install prompt moves into the browse controller (it owns the
install now). Shared relaunch logic (`_after_change`) is factored so both can
use it — move it to a small helper if needed, otherwise duplicate the few lines.

## Data flow

```
[Manage Plugins] Install Plugin… 
   -> open Browse Plugins (livemodal)
       init: run_with_wait( search_channel )   # worker thread, modal progress
              -> write appdata/plugin_index.json
              -> read it back -> build AvailablePackage rows -> table
              (fetch fails -> read cached json, stale=True, "offline" note)
   select row + [More details] -> details_text = format_details(selected)
   [Install] -> consent confirm
            -> run_with_wait( install_from_channel(name, channel_url) )
            -> success -> relaunch prompt
```

## Error handling

- `search_channel` subprocess/parse failure → `InstallError`; model falls back to
  cached index and flags `stale`. If there's no cache either, show an error and
  an empty table.
- `install_from_channel` failure → snapshot/restore rollback (as today); the
  consent/worker path surfaces the error via the existing error dialog.
- Empty channel → empty table (no crash).
- All subprocess calls go through `_run`, which raises `InstallError` with
  stderr/stdout on non-zero exit.

## Testing

- Unit: `format_details` field mapping (size→KiB, timestamp→UTC, deps),
  including missing fields.
- Unit: `search_channel` parses the real JSON shape (subdir-keyed, flattened)
  and writes the cache; stdout-with-leading-warnings is handled (JSON located).
- Unit: `read_cached_index` returns `[]` when the file is absent.
- Manual: open Browse Plugins, fetch the live channel, More details, install
  `scipy_analysis`, confirm relaunch prompt; simulate offline (bad URL) → cached
  list + offline note.

## Reuse

- `run_with_wait` (modal, on-top progress) for both fetch and install.
- `ObjectColumn` (themed) from `microdrop_utils.traitsui_qt_helpers`.
- `SafeCancelTableHandler` base (Escape deselects, doesn't close).
- `pyface_wrapper` dialogs (`confirm`/`information`/`error`, `YES`).
- Existing `_snapshot`/`_restore`/`_ensure_channel_registered` install plumbing.
