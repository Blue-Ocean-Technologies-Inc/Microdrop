# Plugin-as-conda-package — feasibility spike (pixi-build-python + entry points)

**Date:** 2026-06-26
**Status:** Approved (design discussed + approved in conversation)
**Branch:** `feat/plugin_management` (Microdrop submodule)
**Tracks:** Microdrop issue #491 (alternative to the custom-manifest install path).

## Problem & goal

The current plugin-install system is a lot of custom machinery: a `.microdrop_plugin`
zip format, a hand-rolled hardened installer (zip-slip/allowlist/consent), extraction into
app-data `installed_plugins/` with bespoke per-plugin `sys.path` wiring, JSON-manifest
directory discovery, and a `pixi_env.py` layer that mutates the pixi manifest to add a
plugin's dependencies. That last layer in particular has been repeatedly fragile (CLI
output scraping; the per-plugin `sys.path` shadowing bug).

**Goal of this spike:** prove that a MicroDrop plugin can instead be a **real conda package**
built with the **`pixi-build-python`** backend that **declares its own dependencies** (scipy)
and is **discovered via standard Python entry points** — so pixi does the dependency
resolution and install, and `importlib.metadata` does the discovery. If it works end-to-end,
it validates that we could later replace the custom zip/manifest/app-data/feature-wiring
system with standard packaging. This spike is **additive and reversible**: the existing
system is left fully intact.

## Background — why rethink

The custom system grew to solve "install a plugin that needs packages we don't have," but
that is exactly what a package manager already does. Standard Python/conda packaging gives,
for free: dependency resolution, install into `site-packages`, versioning, a lockfile, and
entry-point discovery. The custom code we wrote to approximate those is the part that keeps
breaking.

## Research findings (verified against the two references)

- **pixi build backends** (`pixi-build-python`): a Python project gets a `[package]` section
  + `[package.build.backend] name = "pixi-build-python"`; the backend wraps a PEP 517 build
  (e.g. hatchling) to produce a **conda** package. A consuming workspace references it as a
  `path`/`git`/`url` dependency and pixi **auto-builds and installs it into the environment**
  on `pixi install`/`pixi run`. Requires the workspace `preview = ["pixi-build"]` flag (the
  feature is in preview).
- **Python entry points**: a plugin package declares
  `[project.entry-points."microdrop.plugins"]`; the host discovers them at runtime with
  `importlib.metadata.entry_points(group="microdrop.plugins")` and `ep.load()`. This is the
  standard-library-blessed discovery mechanism — no directory walking.
- A plugin's third-party deps are declared as the package's dependencies; installing the
  package resolves them. **scipy comes along automatically** — no `pixi_env.py`.

Sources: pixi build backends / getting-started, packaging.python.org "creating and
discovering plugins", pixi pyproject.toml reference.

## Approach (the spike)

Repackage the existing `scipy_analysis` demo (reusing `plugin.py` / `dock_pane.py`
**verbatim**) as a buildable pixi conda package, declare it as a `microdrop.plugins` entry
point, keep the group/topic metadata as a **TOML** package-data manifest, install it with
pixi (which pulls in scipy), discover it via entry points, and load it through the
**existing** `PluginGroupManager` runtime (unchanged). Validate in ordered checkpoints, with
the entry-point-propagation question as the explicit go/no-go.

The spike swaps **install + dependency-resolution + discovery** only. The runtime hot-load
(`PluginGroupManager.enable/disable` + reactive dock-pane mounting) is **reused as-is**.

## Components

### A. The buildable plugin package

A new, self-contained directory (does not touch the existing `examples/demo_plugins/
scipy_analysis/` archive demo):

```
examples/demo_plugins/scipy_analysis_pkg/
  pyproject.toml
  scipy_analysis/
    __init__.py
    plugin.py              # copied verbatim from the existing demo
    dock_pane.py           # copied verbatim from the existing demo
    microdrop_plugin.toml  # group/topic metadata, shipped as package data
```

### B. `pyproject.toml` (the buildable package)

```toml
[project]
name = "scipy_analysis"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["scipy>=1.10"]          # PEP 621 (for the wheel build metadata)

[project.entry-points."microdrop.plugins"]
scipy_analysis = "scipy_analysis"        # value = the importable package marking it a plugin

[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[package]
name = "scipy_analysis"
version = "0.1.0"

[package.build.backend]
name = "pixi-build-python"
version = "0.*"

[package.host-dependencies]
hatchling = "*"

[package.run-dependencies]
scipy = ">=1.10"                          # conda run-dep — the operative one pixi resolves
```

Note the deliberate redundancy: scipy appears in `[project.dependencies]` (PEP 621, consumed
by hatchling for wheel metadata) and `[package.run-dependencies]` (the conda run-dependency
pixi resolves against conda-forge). Checkpoint 1 confirms which path actually installs scipy;
the conda run-dependency is expected to be the operative one.

### C. `microdrop_plugin.toml` (TOML manifest, package data)

Same shape as today's JSON manifest, in TOML, living inside the package so it ships as
package data:

```toml
schema_version = 1
name = "scipy_analysis"
label = "Scipy Random Analysis (conda-package spike)"
version = "0.1.0"

[[groups]]
name = "scipy_analysis"
label = "Scipy Random Analysis (dock pane)"
plugins = ["scipy_analysis.plugin:ScipyAnalysisPlugin"]
enabled_key = "microdrop.scipy_analysis_enabled"
```

Read with stdlib `tomllib` (read-only — no tomlkit needed). The existing manifest dataclasses
are reused via a small dict adapter so JSON and TOML manifests yield the same
`PluginManifest`/`PluginGroupSpec` objects.

### D. Entry-point discovery (new, flag-gated)

A new module `plugin_management/entry_point_discovery.py`:

```python
import importlib.metadata as md
import importlib.resources as ir
import tomllib

ENTRY_POINT_GROUP = "microdrop.plugins"

def discover_entry_point_manifests():
    """Yield (PluginManifest, source_label) for every installed package that
    advertises a microdrop.plugins entry point and ships a microdrop_plugin.toml."""
    out = []
    for ep in md.entry_points(group=ENTRY_POINT_GROUP):
        pkg = ep.value                      # e.g. "scipy_analysis"
        res = ir.files(pkg) / "microdrop_plugin.toml"
        data = tomllib.loads(res.read_text(encoding="utf-8"))
        out.append((manifest_from_dict(data), f"entry-point:{pkg}"))
    return out
```

`manifest_from_dict(data)` is the shared dict→dataclass adapter (factored out of the existing
JSON `load_manifest`). Discovery is **flag-gated** (e.g. env var
`MICRODROP_ENTRYPOINT_PLUGINS=1`) and runs **in addition to** the existing path-based
discovery, so the current system is undisturbed. The resulting `PluginGroup`s feed the
existing `PluginGroupManager` unchanged.

### E. Install + relaunch flow

1. Add the plugin as a path dependency to the **main** workspace
   (`microdrop-py/pyproject.toml`): `[workspace] preview = ["pixi-build"]` and
   `[tool.pixi.dependencies] scipy_analysis = { path = "src/examples/demo_plugins/scipy_analysis_pkg" }`.
   `pixi install` builds the conda package via `pixi-build-python` and installs it **+ scipy**
   into the **default** environment.
2. **Relaunch** the app (the running interpreter can't import the just-installed package /
   scipy). Reuse the existing relaunch helper, re-execing the normal launch (default env, no
   `-e` needed).
3. With `MICRODROP_ENTRYPOINT_PLUGINS=1`, the app discovers the plugin via its entry point,
   reads the TOML manifest from package data, and the group appears in Manage Plugins; enabling
   it mounts the dock pane (scipy imports).

For the spike, steps 1–3 are first driven from the **CLI** (fastest path to the go/no-go);
a minimal "install via UI" action (`pixi add` the path dep, then offer relaunch) is wired only
**after** the mechanism is proven (checkpoints 1–3 green).

## Validation checkpoints (ordered; stop at first failure)

1. **Build + install + native deps.** `pixi install` builds the package with
   `pixi-build-python` and lands `scipy_analysis` + scipy in the default env. (Validates the
   build backend + native dependency resolution on win-64, pixi 0.63.2.)
2. **Entry-point propagation — GO/NO-GO.** After install,
   `importlib.metadata.entry_points(group="microdrop.plugins")` returns the plugin. (The real
   unknown: does the preview `pixi-build-python` backend carry `[project.entry-points]` into the
   installed conda package's dist metadata?)
3. **Discovery → existing runtime.** The TOML manifest is read from package data, builds the
   same `PluginGroup` the manager consumes, and `enable` mounts the dock pane (scipy works).
4. **Relaunch UX.** Install → relaunch → enable works from a running app; then the minimal UI
   install action.

## What stays untouched (scope guards)

The `.microdrop_plugin` zip format, `installer.py`, `manifest.py` (JSON), `paths.py`,
`pixi_env.py`, app-data extraction, and the existing `scipy_analysis` archive demo all remain.
The spike adds: the `scipy_analysis_pkg/` buildable package, `entry_point_discovery.py`, the
`manifest_from_dict` adapter, and a flag-gated discovery hook. Nothing existing is removed or
rewired.

## Isolation decision

The spike installs into the **default** environment (simplest; the path dep is a normal
conda dependency). This permanently adds scipy to the base env — accepted for the spike and
**reverted with `pixi remove scipy_analysis`** (or `git checkout` of pyproject/lock). A
dedicated plugins environment is a question for the eventual full design, not the spike.

## Risks & fallbacks

- **Entry-point propagation (checkpoint 2)** is the primary risk. If `pixi-build-python` does
  not surface `[project.entry-points]` in installed metadata, fallbacks to evaluate: (a) a
  naming/namespace convention for discovery (`pkgutil`/namespace package) with the TOML still
  as the config; (b) a console/other entry-point group that does propagate; (c) declaring the
  entry point in the conda recipe the backend generates. Record the outcome either way.
- **Preview-feature churn:** `pixi-build` is preview; pin behavior to pixi 0.63.2 and note any
  version sensitivity.
- **Workspace mutation:** the spike dirties `microdrop-py/pyproject.toml` + `pixi.lock` (the
  build path dep). This is in the **outer** repo; keep the change uncommitted/local and document
  the `pixi remove` revert.

## Out of scope (for the spike)

Replacing or removing any current machinery; distribution channels (prefix.dev/PyPI/GitHub);
a dedicated plugins environment; consent/security hardening for package installs; multi-plugin
or multi-group packages; the full migration design. Those are decided only if the spike's
checkpoints pass.

## Verification

Per project convention (no pytest): `py_compile` + import smokes for the new discovery module;
a CLI walk of checkpoints 1–3 (`pixi install`, an `importlib.metadata.entry_points` probe, a
manifest-read + `PluginGroup` build); and a manual GUI pass for checkpoint 4 (Redis + relaunch
+ enable → dock pane). The pixi build/install steps run against the **real** workspace
(intended for the spike) and are reverted with `pixi remove` afterward.
