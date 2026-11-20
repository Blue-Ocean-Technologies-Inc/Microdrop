# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Throwaway git repositories shaped like the MicroDrop source: release tags
of every kind, and clones free to mutate. ``conftest.py`` imports the
fixtures, so every test module here can request them."""

# Standard library imports.
import subprocess

# Third-party imports.
import pytest

FORCED_PULL_HELPER = "def self_update_source_repo(): pass\n"


def run_git(cwd, *args):
    """Run a setup git command in ``cwd``, failing the test when it fails."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )


def _isolate(repo, hooks):
    """Keep this machine's global git config (signing, hooks) out of ``repo``."""
    run_git(repo, "config", "user.name", "Source Version Tests")
    run_git(repo, "config", "user.email", "tests@example.invalid")
    run_git(repo, "config", "commit.gpgsign", "false")
    run_git(repo, "config", "tag.gpgsign", "false")
    run_git(repo, "config", "core.hooksPath", hooks.as_posix())


def clone_repo(source, destination):
    """A fresh clone of the ``source_repo`` fixture at ``destination``."""
    hooks = source.parent / "no-hooks"

    run_git(
        destination.parent,
        "clone",
        "--config",
        f"core.hooksPath={hooks.as_posix()}",
        str(source),
        destination.name,
    )
    _isolate(destination, hooks)

    return destination


def _commit_release(repo, tag, changelog, annotated=True):
    """Prepend ``tag``'s section to the changelog, commit everything, tag it."""
    section = (
        f"## [{tag}](https://example.invalid/compare/{tag}) (2026-01-01)\n\n"
        f"- the {tag} release\n\n"
    )
    changelog = section + changelog

    (repo / "CHANGELOG.md").write_text(changelog)
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", f"chore: release {tag}")

    if annotated:
        run_git(repo, "tag", "-a", tag, "-m", tag)
    else:
        run_git(repo, "tag", tag)

    return changelog


@pytest.fixture(scope="module")
def source_repo(tmp_path_factory):
    """A repository with four release tags of each kind, odd tags, and an
    untagged commit on top."""
    root = tmp_path_factory.mktemp("source_version")
    hooks = root / "no-hooks"
    repo = root / "source"

    hooks.mkdir()
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    _isolate(repo, hooks)

    helpers = repo / "microdrop_utils" / "app_setup_helpers.py"

    helpers.parent.mkdir()
    helpers.write_text("x = 1\n")
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "chore: release v1.0.0")
    run_git(repo, "tag", "-a", "v1.0.0", "-m", "v1.0.0")

    helpers.write_text(FORCED_PULL_HELPER)
    changelog = _commit_release(repo, "v1.1.0", "", annotated=False)

    panel = repo / "app_updates" / "plugin.py"

    panel.parent.mkdir()
    panel.write_text("PANEL = True\n")
    changelog = _commit_release(repo, "v1.2.0", changelog)

    _commit_release(repo, "v1.10.0", changelog)
    run_git(repo, "tag", "v2.0.0rc1")
    run_git(repo, "tag", "nightly")

    (repo / "README.md").write_text("unreleased work\n")
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "feat: unreleased work")

    return repo


@pytest.fixture
def clone(source_repo, tmp_path):
    """A fresh clone of ``source_repo``, on ``main``, free to mutate."""
    return clone_repo(source_repo, tmp_path / "clone")


@pytest.fixture
def clone_at_v1_2(clone):
    """``clone`` detached at ``v1.2.0``, an older release with the panel."""
    run_git(clone, "checkout", "--detach", "v1.2.0")

    return clone
