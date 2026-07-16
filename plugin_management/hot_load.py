"""Apply a freshly-installed plugin to the LIVE app instead of relaunching.

``pixi install`` writes into the same site-packages the running interpreter
imports from, so a brand-new package is importable without a restart —
``enable()`` already imports never-before-seen plugin code every time a group
is toggled on. What is NOT safe is upgrading or removing an already-imported
package: modules cannot be un-imported, live objects keep their old classes,
and on Windows a loaded .pyd/.dll cannot be replaced.

Two INDEPENDENT checks gate the fast path:

1. No package OTHER than the target dist itself may change or vanish in the
   env diff. The target changing itself (an in-place version change) is fine
   *because of check 2*: callers unload + ``purge_plugin_modules`` the plugin
   first, so its fresh code is genuinely importable.
2. None of the modules ``enable()`` would import may already be in
   ``sys.modules``. The diff alone reports a reinstall-after-uninstall as a
   pure addition, but ``import_module`` would hand back the stale module and
   silently run the old code under the new version's name.

Anything unexpected refuses, and the caller falls back to the relaunch
prompt — always correct, just slower. A refusal returns its REASON (a short
human-readable string, also logged) so the relaunch dialog can say why the
change could not be applied live instead of looking like arbitrary nagging.
"""
import importlib
import importlib.metadata as importlib_metadata
import sys

from plugin_management.entry_point_discovery import (
    discover_entry_point_manifests)
from plugin_management.group_manager import PluginGroupManager
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _top_modules(plugin_specs):
    """The top-level module of each ``"module.path:ClassName"`` spec — exactly
    what ``group_manager._resolve_plugin_class`` imports. Derived from the
    specs rather than by mapping package names to modules — conda names,
    python dist names and module names all differ, and native libs map to no
    dist at all, so any mapping-based check under-reports in the unsafe
    direction."""
    return {spec.partition(":")[0].split(".")[0] for spec in plugin_specs}


def _live_modules(manifest, already_imported):
    """Top-level modules ``enable()`` would import that were ALREADY loaded
    before this install — i.e. stale code we cannot replace in-process.

    ``already_imported`` MUST be a snapshot of ``sys.modules`` taken before
    discovery runs, NOT a live read. ``discover_entry_point_manifests()``
    resolves each entry point's package data via
    ``importlib.resources.files(ep.module)``, which *imports that module* — so
    a live read would report the module discovery itself had just imported and
    refuse every install. See ``_hot_load_installed``."""
    specs = [p for group in manifest.groups for p in group.plugins]
    for top in sorted(_top_modules(specs)):
        if top in already_imported:
            yield top


def _dist_top_modules(dist_name):
    """Every top-level module the installed distribution SHIPS, from its file
    RECORD. The group specs name only the plugin-class modules; a dist may
    ship additional top-level helper packages those modules import — purging
    by specs alone leaves them cached, and the fresh re-import silently binds
    old helper code under the new version. Empty set if not installed."""
    try:
        dist = importlib_metadata.distribution(dist_name)
    except importlib_metadata.PackageNotFoundError:
        return set()
    tops = set()
    for f in dist.files or ():
        first = f.parts[0] if f.parts else ""
        if not first or first.endswith((".dist-info", ".data")):
            continue
        if len(f.parts) == 1:
            if first.endswith(".py"):
                tops.add(first[:-3])
        else:
            tops.add(first)
    return tops


def purge_plugin_modules(plugin_specs, dist_name=""):
    """Drop the plugin's top-level modules (and all their submodules) from
    ``sys.modules`` so a later install re-imports FRESH code from disk instead
    of binding to the cached, now-stale module objects.

    Purges the union of the spec-derived tops and — when ``dist_name`` is
    given and still installed — every top-level module the distribution's
    RECORD ships, so helper packages outside the specs cannot survive as
    stale code.

    Call only after the plugin's groups are disabled and deregistered. Safe
    because MicroDrop plugins are fully isolated (decoupled via dramatiq
    topics / app_globals, no cross-plugin imports — they can even run as
    separate processes), so once a plugin's own instances are torn down
    nothing else holds references into its modules. This is what lets an
    install → uninstall → reinstall cycle, and an in-place version change,
    hot-load instead of demanding a relaunch."""
    tops = _top_modules(plugin_specs) | _dist_top_modules(dist_name)
    purged = [name for name in list(sys.modules)
              if name.split(".")[0] in tops]
    for name in purged:
        del sys.modules[name]
    if purged:
        logger.info(f"purged {len(purged)} module(s) under {sorted(tops)} "
                    f"for reinstall")
    return purged


def hot_load_installed(application, manager, dist_name, diff) -> str | None:
    """Register + enable a just-installed distribution's plugin groups on the
    live application.

    GUI THREAD ONLY: mutates the manager's traits and fires the
    TASK_EXTENSIONS delta that LiveTaskExtensionsController reconciles into
    mounted dock panes.

    Returns None when the plugin is live and no relaunch is needed; otherwise
    a short human-readable reason the fast path was refused, for the caller
    to show alongside the relaunch prompt."""
    try:
        return _hot_load_installed(application, manager, dist_name, diff)
    except Exception:
        logger.exception(
            f"hot-load of '{dist_name}' failed; falling back to relaunch")
        return "an unexpected error occurred (see the log)"


def _refuse(dist_name, reason):
    """Log a refusal and return its reason for the relaunch dialog."""
    logger.info(f"hot-load refused for '{dist_name}': {reason}")
    return reason


def _hot_load_installed(application, manager, dist_name, diff):
    norm = PluginGroupManager._norm_dist
    if diff is None:
        return _refuse(dist_name,
                       "the environment change could not be determined")
    # The target dist changing ITSELF (in-place version change) is allowed:
    # the caller unloads + purges its modules first, and the sys.modules
    # guard below still refuses if that didn't happen. Any OTHER package
    # moving may be live in this interpreter — relaunch.
    moved = sorted(diff.changed) + sorted(diff.removed)
    blocking = [m for m in moved if norm(m) != norm(dist_name)]
    if blocking:
        return _refuse(dist_name, f"existing packages were changed or "
                                  f"removed: {', '.join(blocking)}")

    # Snapshot sys.modules BEFORE discovery. discover_entry_point_manifests()
    # reads each entry point's package-data manifest via
    # importlib.resources.files(ep.module), which IMPORTS that module — so a
    # guard reading sys.modules afterwards would always see the plugin's own
    # module and refuse every install. What we need to know is what was stale
    # *before* this install, and only a pre-discovery snapshot answers that.
    already_imported = set(sys.modules)

    # The metadata cache is mtime-keyed and would self-invalidate, but the
    # FileFinder / sys.path_importer_cache layer that enable()'s
    # import_module goes through is not.
    importlib.invalidate_caches()

    mine = [(m, d) for m, d in discover_entry_point_manifests()
            if norm(d) == norm(dist_name)]
    if not mine:
        return _refuse(dist_name, "no plugin manifest was found for it")

    for manifest, _ in mine:
        live = sorted(set(_live_modules(manifest, already_imported)))
        if live:
            return _refuse(dist_name, f"{', '.join(live)} is already loaded "
                                      f"from an earlier install")

    names = []
    try:
        for manifest, dist in mine:
            manager.register_manifest(manifest, dist_name=dist)
            names += [g.name for g in manifest.groups]
    except RuntimeError as e:
        return _refuse(dist_name, str(e))

    # apply() rather than enable(): it is the public reconcile entry point AND
    # it persists the enabled flag, so a hot-installed plugin comes back on
    # the next launch exactly like a toggled one.
    manager.apply(application, {n: True for n in names})

    not_loaded = [n for n in names if not manager.is_loaded(n)]
    if not_loaded:
        return _refuse(dist_name, f"plugin groups failed to load: "
                                  f"{', '.join(not_loaded)}")

    logger.info(f"hot-loaded '{dist_name}': enabled groups {names}")
    return None
