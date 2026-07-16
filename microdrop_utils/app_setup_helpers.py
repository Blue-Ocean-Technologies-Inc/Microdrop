import os
import shutil
import subprocess
import sys
from pathlib import Path

from microdrop_utils.broker_server_helpers import configure_dramatiq_broker
from logger.logger_service import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Set to any non-empty value to skip the startup git self-update — for
#: developer machines where the IDE or the launcher scripts manage the repo.
SKIP_GIT_UPDATE_ENV_VAR = "MICRODROP_SKIP_GIT_UPDATE"

#: Per-command timeout for the startup self-update, so a flaky network can
#: delay app startup by at most this long.
GIT_SELF_UPDATE_TIMEOUT_S = 30

#: The branch the self-update checks out when none is checked out (a freshly
#: initialized submodule sits on a detached HEAD, where `git pull` refuses).
SOURCE_DEFAULT_BRANCH = "main"


def _git(repo_root, *args):
    """Run a git command in ``repo_root``, captured, with the update timeout."""
    return subprocess.run(
        ["git", *args], cwd=str(repo_root), capture_output=True, text=True,
        timeout=GIT_SELF_UPDATE_TIMEOUT_S)


def self_update_source_repo(repo_root=PROJECT_ROOT,
                            default_branch=SOURCE_DEFAULT_BRANCH):
    """Best-effort git self-update of the MicroDrop source repo — a backstop
    so the app keeps itself current even when launched without the launcher
    scripts (IDE, custom shortcut, `pixi run microdrop` directly).

    The running process already imported its modules, so a pull cannot change
    THIS session — when the pull moves HEAD, a warning tells the user the
    updates take effect the next time they start the app.

    Mirrors the launcher scripts' semantics:

    - no branch checked out (detached HEAD — every freshly initialized
      submodule) -> check out ``default_branch`` first;
    - ``pull --ff-only --autostash`` — never starts a merge the user would
      have to resolve, and carries legitimately-dirty tracked files (the
      installed-plugin pins in the parent's pyproject) across the pull;
    - every failure is a logged warning, never a blocked launch.

    Skipped when ``MICRODROP_SKIP_GIT_UPDATE`` is set, when git or the
    ``.git`` link is absent (frozen/tarball installs), or on any error.
    """
    if os.environ.get(SKIP_GIT_UPDATE_ENV_VAR):
        logger.info(f"source self-update skipped ({SKIP_GIT_UPDATE_ENV_VAR} is set)")
        return
    # A submodule's .git is a FILE pointing at the real git dir — exists(),
    # not is_dir().
    if shutil.which("git") is None or not (Path(repo_root) / ".git").exists():
        logger.debug("source self-update skipped: no git or not a checkout")
        return
    try:
        branch = _git(repo_root, "branch", "--show-current").stdout.strip()
        if not branch:
            logger.warning(f"no branch checked out in {repo_root} (detached "
                           f"HEAD); checking out {default_branch}")
            checkout = _git(repo_root, "checkout", default_branch)
            if checkout.returncode != 0:
                logger.warning(f"could not check out {default_branch}: "
                               f"{checkout.stderr.strip()}")
                return
        before = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
        pull = _git(repo_root, "pull", "--ff-only", "--autostash")
        if pull.returncode != 0:
            logger.warning(f"source self-update pull failed (offline, or "
                           f"local changes/diverged history): "
                           f"{pull.stderr.strip() or pull.stdout.strip()}")
            return
        after = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
        if before != after:
            logger.warning(
                f"MicroDrop source updated ({before[:8]} -> {after[:8]}). "
                f"You will receive the updates the next time you start the "
                f"app.")
        else:
            logger.info("MicroDrop source is up to date")
    except Exception as e:
        logger.warning(f"source self-update failed: {e}")


def microdrop_runner_setup():
    """
    Common setup for all MicroDrop runner scripts.

    Configures the Dramatiq broker from redis_settings.json, adds the project
    root to sys.path so submodules are importable, and runs the best-effort
    git self-update (see :func:`self_update_source_repo` — updates apply on
    the NEXT launch, this one is already imported).

    Must be called before importing any modules that use dramatiq.get_broker().
    """
    configure_dramatiq_broker()
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    self_update_source_repo()
