"""Apply a freshly-installed plugin to the LIVE app instead of relaunching.

``pixi install`` writes into the same site-packages the running interpreter
imports from, so a brand-new package is importable without a restart —
``enable()`` already imports never-before-seen plugin code every time a group
is toggled on. What is NOT safe is upgrading or removing an already-imported
package: modules cannot be un-imported, live objects keep their old classes,
and on Windows a loaded .pyd/.dll cannot be replaced.

Two INDEPENDENT checks gate the fast path:

1. The env diff must be purely additive (``EnvDiff.is_pure_addition``).
2. None of the modules ``enable()`` would import may already be in
   ``sys.modules``. The diff alone reports a reinstall-after-uninstall as a
   pure addition, but ``import_module`` would hand back the stale module and
   silently run the old code under the new version's name.

Anything unexpected returns False and the caller falls back to the relaunch
prompt — always correct, just slower.
"""
import importlib
import sys

from plugin_management.entry_point_discovery import (
    discover_entry_point_manifests)
from plugin_management.group_manager import PluginGroupManager
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _live_modules(manifest):
    """Top-level modules ``enable()`` would import that are ALREADY loaded.

    Keys on exactly what ``group_manager._resolve_plugin_class`` imports,
    rather than mapping package names to modules — conda names, python dist
    names and module names all differ, and native libs map to no dist at all,
    so any mapping-based check under-reports in the unsafe direction."""
    for spec in manifest.groups:
        for plugin_spec in spec.plugins:          # "module.path:ClassName"
            top = plugin_spec.partition(":")[0].split(".")[0]
            if top in sys.modules:
                yield top


def hot_load_installed(application, manager, dist_name, diff) -> bool:
    """Register + enable a just-installed distribution's plugin groups on the
    live application.

    GUI THREAD ONLY: mutates the manager's traits and fires the
    TASK_EXTENSIONS delta that LiveTaskExtensionsController reconciles into
    mounted dock panes.

    Returns True when the plugin is live and no relaunch is needed; False
    means the caller must offer the relaunch prompt."""
    try:
        return _hot_load_installed(application, manager, dist_name, diff)
    except Exception:
        logger.exception(
            f"hot-load of '{dist_name}' failed; falling back to relaunch")
        return False


def _hot_load_installed(application, manager, dist_name, diff):
    if diff is None or not diff.is_pure_addition:
        logger.info(f"hot-load refused for '{dist_name}': the env change is "
                    f"not purely additive")
        return False

    # The metadata cache is mtime-keyed and would self-invalidate, but the
    # FileFinder / sys.path_importer_cache layer that enable()'s
    # import_module goes through is not.
    importlib.invalidate_caches()

    norm = PluginGroupManager._norm_dist
    mine = [(m, d) for m, d in discover_entry_point_manifests()
            if norm(d) == norm(dist_name)]
    if not mine:
        logger.warning(
            f"hot-load refused: no manifest discovered for '{dist_name}'")
        return False

    for manifest, _ in mine:
        live = sorted(set(_live_modules(manifest)))
        if live:
            logger.info(f"hot-load refused for '{dist_name}': modules already "
                        f"imported: {live}")
            return False

    names = []
    try:
        for manifest, dist in mine:
            manager.register_manifest(manifest, dist_name=dist)
            names += [g.name for g in manifest.groups]
    except RuntimeError as e:
        logger.warning(f"hot-load refused for '{dist_name}': {e}")
        return False

    # apply() rather than enable(): it is the public reconcile entry point AND
    # it persists the enabled flag, so a hot-installed plugin comes back on
    # the next launch exactly like a toggled one.
    manager.apply(application, {n: True for n in names})

    not_loaded = [n for n in names if not manager.is_loaded(n)]
    if not_loaded:
        logger.warning(f"hot-load of '{dist_name}' left groups unloaded: "
                       f"{not_loaded}; relaunch needed")
        return False

    logger.info(f"hot-loaded '{dist_name}': enabled groups {names}")
    return True
