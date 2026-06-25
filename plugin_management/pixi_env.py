"""Add/remove a plugin's dependencies in the pixi-managed workspace.

Each dependency-bearing plugin gets a feature ``plugin-<name>``; the
``microdrop-plugins`` environment = default + every such feature. Adding deps is
conflict-checked with ``pixi lock`` and snapshot/rolled-back on failure. Qt-free
service; the command BUILDERS are pure (unit-testable) and ``_run`` is the only
side-effecting part.

WARNING: these commands edit the workspace ``pyproject.toml`` + ``pixi.lock``.
Never invoke the mutating helpers outside a real install / a throwaway test
project.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The pixi workspace root (microdrop-py/, parent of src/) — has pyproject.toml.
WORKSPACE_DIR = Path(__file__).resolve().parents[2]

PLUGINS_ENV = "microdrop-plugins"
FEATURE_PREFIX = "plugin-"


class PixiError(Exception):
    """A pixi command failed."""


class PixiConflictError(PixiError):
    """The workspace could not be solved with the plugin's dependencies."""


def feature_name(manifest_name: str) -> str:
    return FEATURE_PREFIX + manifest_name


# --- pure command builders (argv after "pixi"; unit-testable) --------

def add_conda_cmd(feature, specs):
    return ["add", "--no-progress", "--feature", feature, *specs]


def add_pypi_cmd(feature, specs):
    return ["add", "--no-progress", "--feature", feature, "--pypi", *specs]


def env_add_cmd(env, features):
    cmd = ["workspace", "environment", "add", env, "--force"]
    for f in features:
        cmd += ["--feature", f]
    return cmd


def env_remove_cmd(env):
    return ["workspace", "environment", "remove", env]


def feature_remove_cmd(feature):
    return ["workspace", "feature", "remove", feature]


def feature_list_cmd():
    return ["workspace", "feature", "list"]


def lock_cmd():
    return ["lock", "--no-progress"]


def install_env_cmd(env):
    return ["install", "--no-progress", "-e", env]


# --- runner ------------------------------------------------------------

def _run(args, *, cwd=None):
    """Run ``pixi <args>`` non-interactively in the workspace. Raises PixiError
    on a nonzero exit, with stderr in the message."""
    proc = subprocess.run(
        ["pixi", *args], cwd=str(cwd or WORKSPACE_DIR),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise PixiError(
            f"`pixi {' '.join(args)}` failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc


def _plugin_features(cwd=None):
    """The current ``plugin-*`` feature names from the manifest."""
    out = _run(feature_list_cmd(), cwd=cwd).stdout
    return sorted(
        line.strip() for line in out.splitlines()
        if line.strip().startswith(FEATURE_PREFIX)
    )


def _snapshot(cwd):
    files = {}
    for name in ("pyproject.toml", "pixi.lock"):
        p = Path(cwd) / name
        if p.exists():
            files[name] = p.read_bytes()
    return files


def _restore(cwd, snapshot):
    for name, data in snapshot.items():
        (Path(cwd) / name).write_bytes(data)


def add_plugin_dependencies(manifest_name, conda, pypi, *, cwd=None):
    """Add a plugin's deps to its feature + the microdrop-plugins env, conflict-
    checked. Snapshot/restore pyproject.toml + pixi.lock on any failure. Raises
    PixiConflictError if the workspace can't be solved with the deps."""
    cwd = Path(cwd or WORKSPACE_DIR)
    feat = feature_name(manifest_name)
    snapshot = _snapshot(cwd)
    try:
        if conda:
            _run(add_conda_cmd(feat, list(conda)), cwd=cwd)
        if pypi:
            _run(add_pypi_cmd(feat, list(pypi)), cwd=cwd)
        _run(env_add_cmd(PLUGINS_ENV, _plugin_features(cwd=cwd)), cwd=cwd)
        try:
            _run(lock_cmd(), cwd=cwd)
        except PixiError as e:
            raise PixiConflictError(
                f"'{manifest_name}' dependencies could not be solved against the "
                f"environment: {e}"
            ) from e
        _run(install_env_cmd(PLUGINS_ENV), cwd=cwd)
    except Exception:
        _restore(cwd, snapshot)
        raise
    logger.info(f"added dependencies for plugin '{manifest_name}' to {PLUGINS_ENV}")


def remove_plugin_dependencies(manifest_name, *, cwd=None):
    """Drop a plugin's feature + update/remove the microdrop-plugins env.
    The env must be updated first (to drop the feature from it) before pixi
    will allow the feature itself to be removed without an interactive prompt.
    Best-effort; logs and continues on per-step failure."""
    cwd = Path(cwd or WORKSPACE_DIR)
    feat = feature_name(manifest_name)
    try:
        remaining = [f for f in _plugin_features(cwd=cwd) if f != feat]
        if remaining:
            _run(env_add_cmd(PLUGINS_ENV, remaining), cwd=cwd)
        else:
            _run(env_remove_cmd(PLUGINS_ENV), cwd=cwd)
    except PixiError as e:
        logger.warning(f"updating {PLUGINS_ENV} before removing '{feat}' failed: {e}")
    try:
        _run(feature_remove_cmd(feat), cwd=cwd)
    except PixiError as e:
        logger.debug(f"feature remove for '{feat}' skipped: {e}")
