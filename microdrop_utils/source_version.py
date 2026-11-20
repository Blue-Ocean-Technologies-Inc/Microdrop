# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Git facts about the MicroDrop source checkout, and moving it between
release tags.

A managed checkout — on ``main``, or detached at a release tag or a commit of
``origin/main``, with no local changes to tracked files and no git operation
in progress — is one the app may move itself. Release tags are
``vX.Y.Z`` and come in three kinds, by what their tree holds: the Updates
panel (``HAS_PANEL``), the older startup self-update that forces a pull of
``main`` (``FORCED_PULL``), or neither (``PLAIN``).

This module is Qt-free; every git command runs non-interactively with a
timeout, and only ``fetch_tags`` and ``switch_to`` report failures, as
``SourceVersionError``. The read helpers answer an empty value instead.
"""

# Standard library imports.
import os
import re
import shutil
import subprocess
from collections import namedtuple
from pathlib import Path

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Per-command timeout, so a flaky network delays the caller by at most this.
GIT_TIMEOUT_S = 30

#: The branch a managed checkout follows.
DEFAULT_BRANCH = "main"

#: A release whose tree holds this file ships the Updates panel.
PANEL_MARKER_PATH = "app_updates/plugin.py"

#: A release whose marker file mentions the marker text pulls ``main`` at
#: every startup, so switching to it would not stay put.
FORCED_PULL_MARKER_PATH = "microdrop_utils/app_setup_helpers.py"
FORCED_PULL_MARKER_TEXT = "self_update_source_repo"

#: Checkout states.
MANAGED, DEVELOPMENT, NO_GIT = "managed", "development", "no_git"

#: Files git keeps in its directory while a bisect, rebase, merge, cherry-pick
#: or revert is under way.
OPERATION_MARKERS = (
    "BISECT_LOG",
    "rebase-merge",
    "rebase-apply",
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
)

#: Release tag kinds.
HAS_PANEL, FORCED_PULL, PLAIN = "has_panel", "forced_pull", "plain"

#: A release tag: its ``name`` ("v1.46.0"), ``version`` ((1, 46, 0)), creation
#: ``date`` ("2026-11-18") and ``kind``.
ReleaseTag = namedtuple("ReleaseTag", "name version date kind")

_RELEASE_PATTERN = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


class SourceVersionError(Exception):
    """A git command could not run or failed; ``output`` holds what git
    printed."""

    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


def _git(repo_root, *args, input=None):
    """Run ``git *args`` in ``repo_root`` and return the CompletedProcess.

    Raises SourceVersionError when ``repo_root`` is not a checkout or git
    cannot run (missing, or past ``GIT_TIMEOUT_S``)."""
    command = " ".join(("git", *args))

    # Without its own .git, git would walk up and act on an enclosing
    # repository — the launcher checkout, for an untracked source tree. A
    # submodule's .git is a FILE: exists(), not is_dir().
    if not (Path(repo_root) / ".git").exists():
        raise SourceVersionError(f"`{command}`: {repo_root} is not a git checkout")

    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            input=input,
            stdin=subprocess.DEVNULL if input is None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_S,
            # A console-less app on Windows would flash a window per call.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise SourceVersionError(f"`{command}` could not run: {e}") from e


def _output(repo_root, *args):
    """The stripped stdout of ``git *args``, or "" when it fails."""
    try:
        result = _git(repo_root, *args)
    except SourceVersionError as e:
        logger.warning(f"{e}")

        return ""

    if result.returncode != 0:
        logger.warning(f"`git {' '.join(args)}` failed: {result.stderr.strip()}")

        return ""

    return result.stdout.strip()


def _run_or_raise(repo_root, *args):
    """Run ``git *args``, raising SourceVersionError when it fails."""
    result = _git(repo_root, *args)

    if result.returncode != 0:
        raise SourceVersionError(
            f"`git {' '.join(args)}` exited with code {result.returncode}",
            result.stderr.strip() or result.stdout.strip(),
        )


def parse_release(name):
    """The ``(major, minor, patch)`` of a ``vX.Y.Z`` tag name, or None for
    any other name."""
    match = _RELEASE_PATTERN.fullmatch(name or "")

    if match is None:
        return None

    return tuple(int(part) for part in match.groups())


def is_newer_release(tag_name, built_on_name):
    """Return True when release ``tag_name`` is newer than ``built_on_name``,
    the release a checkout is built on; a checkout built on none (None or
    "") is older than any release."""
    version = parse_release(tag_name)
    built_on = parse_release(built_on_name) or (0, 0, 0)

    return version is not None and version > built_on


def checkout_state(repo_root):
    """The checkout's state and why: ``(MANAGED, "")``, ``(DEVELOPMENT,
    <reason>)``, or ``(NO_GIT, <reason>)``.

    Managed is ``main``, or a detached HEAD exactly at a release tag or on
    ``origin/main``. Local changes to tracked files, a git operation in
    progress (a bisect, a paused rebase), any other branch, and any other
    detached commit are development. Untracked files leave a checkout
    managed — switching tags keeps them."""
    if shutil.which("git") is None:
        return NO_GIT, "git is not installed"

    if not (Path(repo_root) / ".git").exists():
        return NO_GIT, f"{repo_root} is not a git checkout"

    try:
        status = _git(repo_root, "status", "--porcelain", "--untracked-files=no")
        operation_paths = _git(
            repo_root,
            "rev-parse",
            *(option for name in OPERATION_MARKERS for option in ("--git-path", name)),
        )
        head = _git(repo_root, "symbolic-ref", "--short", "-q", "HEAD")
    except SourceVersionError as e:
        return NO_GIT, str(e)

    # A checkout git cannot read is never one to move.
    if status.returncode != 0:
        return NO_GIT, f"git status failed: {status.stderr.strip()}"

    if status.stdout.strip():
        return DEVELOPMENT, "local changes"

    if operation_paths.returncode != 0:
        return NO_GIT, f"git rev-parse failed: {operation_paths.stderr.strip()}"

    # The paths are relative to the checkout, or absolute in a worktree or
    # submodule; joining keeps an absolute one as it is.
    if any(
        (Path(repo_root) / path).exists()
        for path in operation_paths.stdout.splitlines()
    ):
        return DEVELOPMENT, "git operation in progress"

    # Exit 1 is a detached HEAD. Any other failure leaves the branch unknown,
    # and an unknown branch must not pass for a detached, managed one.
    if head.returncode not in (0, 1):
        return NO_GIT, f"git symbolic-ref failed: {head.stderr.strip()}"

    branch = head.stdout.strip()

    if branch == DEFAULT_BRANCH:
        return MANAGED, ""

    if branch:
        return DEVELOPMENT, f"branch {branch}"

    if exact_release(repo_root) or _head_is_on_origin_main(repo_root):
        return MANAGED, ""

    return DEVELOPMENT, f"detached at a commit that is not on {DEFAULT_BRANCH}"


def _head_is_on_origin_main(repo_root):
    """Return True when HEAD is an ancestor of ``origin/main``, and False when
    it is not, that ref is missing, or git fails."""
    try:
        ancestor = _git(
            repo_root,
            "merge-base",
            "--is-ancestor",
            "HEAD",
            f"refs/remotes/origin/{DEFAULT_BRANCH}",
        )
    except SourceVersionError as e:
        logger.warning(f"{e}")

        return False

    return ancestor.returncode == 0


def describe(repo_root):
    """``git describe --tags --always --dirty`` of the checkout, or "" when
    there is no checkout."""
    return _output(repo_root, "describe", "--tags", "--always", "--dirty")


def current_branch(repo_root):
    """The checked-out branch, or "" on a detached HEAD."""
    return _output(repo_root, "branch", "--show-current")


def _newest_release(repo_root, selection):
    """The newest-version release tag among ``git tag <selection> HEAD``, or
    None. Near-miss names (v1.47, v1.2.3.4, v2.0.0rc1) never count."""
    names = _output(repo_root, "tag", selection, "HEAD", "--list", "v*")
    releases = [name for name in names.splitlines() if parse_release(name)]

    return max(releases, key=parse_release, default=None)


def current_release(repo_root):
    """The newest release tag reachable from HEAD, or None. Releases are cut
    along ``main``'s linear history, where that is also the nearest one."""
    return _newest_release(repo_root, "--merged")


def exact_release(repo_root):
    """The release tag HEAD is exactly at (the newest, when several are), or
    None."""
    return _newest_release(repo_root, "--points-at")


def list_release_tags(repo_root):
    """Every release tag as a ``ReleaseTag``, newest version first; [] when
    there are none or git fails.

    Three git commands however many tags there are — one per tag takes
    seconds on Windows."""
    refs = _output(
        repo_root,
        "for-each-ref",
        "--sort=-v:refname",
        # Not refname:short — a branch sharing a tag's name makes that print
        # "tags/<name>", which would drop the tag.
        "--format=%(refname:strip=2) %(creatordate:short)",
        "refs/tags/v*",
    )

    releases = []

    for line in refs.splitlines():
        name, _, date = line.partition(" ")
        version = parse_release(name)

        if version is not None:
            releases.append((name, version, date))

    if not releases:
        return []

    names = [name for name, _version, _date in releases]

    try:
        markers = _git(
            repo_root,
            "cat-file",
            "--batch-check",
            input="".join(f"{name}:{PANEL_MARKER_PATH}\n" for name in names),
        )
        forced = _git(
            repo_root,
            "grep",
            "-l",
            FORCED_PULL_MARKER_TEXT,
            *names,
            "--",
            FORCED_PULL_MARKER_PATH,
        )
    except SourceVersionError as e:
        logger.warning(f"Could not read the release tags: {e}")

        return []

    # git grep exits 1 when nothing matched, which is an answer, not a failure.
    if markers.returncode != 0 or forced.returncode not in (0, 1):
        logger.warning(
            f"Could not read the release tags: "
            f"{markers.stderr.strip() or forced.stderr.strip()}"
        )

        return []

    # One reply line per query line, in order: "<sha> blob <size>" when the
    # file exists, "<query> missing" when it does not.
    with_panel = {
        name
        for name, reply in zip(names, markers.stdout.splitlines())
        if reply.split()[1:2] == ["blob"]
    }

    # Hits are listed as "<tag>:<path>".
    with_forced_pull = {line.partition(":")[0] for line in forced.stdout.splitlines()}

    tags = []

    for name, version, date in releases:
        if name in with_panel:
            kind = HAS_PANEL
        elif name in with_forced_pull:
            kind = FORCED_PULL
        else:
            kind = PLAIN

        tags.append(ReleaseTag(name, version, date, kind))

    return tags


def newest_panel_tag(tags):
    """The first ``HAS_PANEL`` tag of ``tags`` (newest first), or None."""
    return next((tag for tag in tags if tag.kind == HAS_PANEL), None)


def pending_update(repo_root):
    """The release tag a managed checkout should move to: the newest one
    with the Updates panel, when it is newer than the checkout's release.
    None otherwise — a checkout past that tag is never moved back to it."""
    if checkout_state(repo_root)[0] != MANAGED:
        return None

    newest = newest_panel_tag(list_release_tags(repo_root))

    if newest is None:
        return None

    if not is_newer_release(newest.name, current_release(repo_root)):
        return None

    return newest


def fetch_tags(repo_root):
    """Fetch the tags of ``origin``. Raises SourceVersionError when that
    fails."""
    # No --force: a release tag re-pointed on origin must fail loudly, not
    # silently replace the local one.
    _run_or_raise(repo_root, "fetch", "--tags", "--quiet", "origin")


def changelog_section(repo_root, tag_name):
    """The ``CHANGELOG.md`` section of release ``tag_name``, as it stands in
    that tag, or "" when the tag has no changelog or no such section."""
    try:
        shown = _git(repo_root, "show", f"{tag_name}:CHANGELOG.md")
    except SourceVersionError as e:
        logger.warning(f"{e}")

        return ""

    # Releases older than the changelog have none, which git reports as a
    # failure; for them no section is the answer.
    if shown.returncode != 0:
        logger.debug(f"No changelog in {tag_name}: {shown.stderr.strip()}")

        return ""

    heading = f"## [{tag_name}]"
    section = []

    for line in shown.stdout.splitlines():
        if section and line.startswith("## "):
            break

        if section or line.startswith(heading):
            section.append(line)

    return "\n".join(section).strip()


def switch_to(repo_root, tag_name):
    """Check out ``tag_name`` on a detached HEAD. Raises SourceVersionError
    when git refuses."""
    _run_or_raise(repo_root, "checkout", "--detach", tag_name)


def return_commands(repo_root):
    """The shell lines that put the checkout back on ``DEFAULT_BRANCH``."""
    return f'cd "{repo_root}"\ngit checkout {DEFAULT_BRANCH}\ngit pull'
