# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""source_version: release tags and their kinds, the checkout state, the
pending update, changelog sections, and moving the checkout between tags —
against real git repositories."""

# Standard library imports.
import re
import shutil
import subprocess

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.source_version import (
    DEVELOPMENT,
    FORCED_PULL,
    HAS_PANEL,
    MANAGED,
    NO_GIT,
    PLAIN,
    SourceVersionError,
    changelog_section,
    checkout_state,
    current_branch,
    describe,
    exact_release,
    fetch_tags,
    list_release_tags,
    parse_release,
    pending_update,
    return_commands,
    switch_to,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)

FORCED_PULL_HELPER = "def self_update_source_repo(): pass\n"


def _run_git(cwd, *args):
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
    _run_git(repo, "config", "user.name", "Source Version Tests")
    _run_git(repo, "config", "user.email", "tests@example.invalid")
    _run_git(repo, "config", "commit.gpgsign", "false")
    _run_git(repo, "config", "tag.gpgsign", "false")
    _run_git(repo, "config", "core.hooksPath", hooks.as_posix())


def _clone(source, destination):
    """A fresh clone of the ``source_repo`` fixture at ``destination``."""
    hooks = source.parent / "no-hooks"
    _run_git(
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
    _run_git(repo, "add", "--all")
    _run_git(repo, "commit", "-m", f"chore: release {tag}")

    if annotated:
        _run_git(repo, "tag", "-a", tag, "-m", tag)
    else:
        _run_git(repo, "tag", tag)

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

    _run_git(repo, "init", "-b", "main")
    _isolate(repo, hooks)

    helpers = repo / "microdrop_utils" / "app_setup_helpers.py"
    helpers.parent.mkdir()
    helpers.write_text("x = 1\n")
    _run_git(repo, "add", "--all")
    _run_git(repo, "commit", "-m", "chore: release v1.0.0")
    _run_git(repo, "tag", "-a", "v1.0.0", "-m", "v1.0.0")

    helpers.write_text(FORCED_PULL_HELPER)
    changelog = _commit_release(repo, "v1.1.0", "", annotated=False)

    panel = repo / "app_updates" / "plugin.py"
    panel.parent.mkdir()
    panel.write_text("PANEL = True\n")
    changelog = _commit_release(repo, "v1.2.0", changelog)

    _commit_release(repo, "v1.10.0", changelog)
    _run_git(repo, "tag", "v2.0.0rc1")
    _run_git(repo, "tag", "nightly")

    (repo / "README.md").write_text("unreleased work\n")
    _run_git(repo, "add", "--all")
    _run_git(repo, "commit", "-m", "feat: unreleased work")

    return repo


@pytest.fixture
def clone(source_repo, tmp_path):
    """A fresh clone of ``source_repo``, on ``main``, free to mutate."""
    return _clone(source_repo, tmp_path / "clone")


def test_parse_release_accepts_only_three_part_versions():
    assert parse_release("v1.46.0") == (1, 46, 0)
    assert parse_release("v2.0.0rc1") is None
    assert parse_release("nightly") is None
    assert parse_release("v1.46") is None


def test_release_tags_are_newest_first_by_version_and_skip_odd_tags(clone):
    tags = list_release_tags(clone)

    assert [t.name for t in tags] == ["v1.10.0", "v1.2.0", "v1.1.0", "v1.0.0"]
    assert [t.version for t in tags] == [(1, 10, 0), (1, 2, 0), (1, 1, 0), (1, 0, 0)]
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", t.date) for t in tags)


def test_tag_kinds(clone):
    assert {t.name: t.kind for t in list_release_tags(clone)} == {
        "v1.10.0": HAS_PANEL,
        "v1.2.0": HAS_PANEL,
        "v1.1.0": FORCED_PULL,
        "v1.0.0": PLAIN,
    }


def test_state_managed_on_main_and_when_detached(clone):
    assert checkout_state(clone) == (MANAGED, "")
    assert current_branch(clone) == "main"

    _run_git(clone, "checkout", "--detach", "v1.2.0")

    assert checkout_state(clone) == (MANAGED, "")
    assert current_branch(clone) == ""


def test_state_development_on_feature_branch(clone):
    _run_git(clone, "checkout", "-b", "feat/x")

    assert checkout_state(clone) == (DEVELOPMENT, "branch feat/x")


def test_state_development_with_modified_tracked_file(clone):
    (clone / "README.md").write_text("edited in the IDE\n")

    assert checkout_state(clone) == (DEVELOPMENT, "local changes")


def test_untracked_files_do_not_make_a_checkout_development(clone):
    (clone / "scratch.txt").write_text("notes\n")

    assert checkout_state(clone) == (MANAGED, "")


def test_state_no_git_without_dot_git(tmp_path):
    assert checkout_state(tmp_path)[0] == NO_GIT
    assert describe(tmp_path) == ""


def test_pending_update_is_none_when_ahead_of_newest_tag(clone):
    assert describe(clone).startswith("v1.10.0-1-g")
    assert pending_update(clone) is None


def test_pending_update_from_older_tag(clone):
    _run_git(clone, "checkout", "--detach", "v1.2.0")

    assert pending_update(clone).name == "v1.10.0"


def test_pending_update_skips_tags_without_the_panel(clone):
    _run_git(clone, "tag", "-d", "v1.2.0", "v1.10.0")
    _run_git(clone, "checkout", "--detach", "v1.0.0")

    assert pending_update(clone) is None


def test_pending_update_is_none_on_development_checkout(clone):
    _run_git(clone, "checkout", "--detach", "v1.2.0")
    (clone / "CHANGELOG.md").write_text("edited in the IDE\n")

    assert checkout_state(clone)[0] == DEVELOPMENT
    assert pending_update(clone) is None


def test_changelog_section_is_only_that_version(clone):
    text = changelog_section(clone, "v1.2.0")

    assert text.startswith("## [v1.2.0]")
    assert "the v1.2.0 release" in text
    assert "v1.1.0" not in text
    assert "v1.10.0" not in text


def test_changelog_section_empty_when_tag_has_no_changelog(clone):
    assert changelog_section(clone, "v1.0.0") == ""


def test_switch_to_detaches_at_tag(clone):
    switch_to(clone, "v1.2.0")

    assert exact_release(clone) == "v1.2.0"
    assert current_branch(clone) == ""


def test_switch_to_raises_on_unknown_tag(clone):
    with pytest.raises(SourceVersionError) as raised:
        switch_to(clone, "v9.9.9")

    assert raised.value.output
    assert current_branch(clone) == "main"


def test_fetch_tags_brings_new_tag(source_repo, clone, tmp_path):
    publisher = _clone(source_repo, tmp_path / "publisher")
    _run_git(publisher, "tag", "v1.11.0")

    assert "v1.11.0" not in [t.name for t in list_release_tags(clone)]

    _run_git(publisher, "push", "origin", "v1.11.0")

    try:
        fetch_tags(clone)
    finally:
        # The source repository is shared by the whole module.
        _run_git(source_repo, "tag", "-d", "v1.11.0")

    assert list_release_tags(clone)[0].name == "v1.11.0"


def test_fetch_tags_raises_without_remote(clone):
    _run_git(clone, "remote", "remove", "origin")

    with pytest.raises(SourceVersionError) as raised:
        fetch_tags(clone)

    assert raised.value.output


def test_list_release_tags_empty_in_repo_without_tags(tmp_path):
    _run_git(tmp_path, "init", "-b", "main")

    assert list_release_tags(tmp_path) == []


def test_return_commands(tmp_path):
    assert return_commands(tmp_path).splitlines() == [
        f'cd "{tmp_path}"',
        "git checkout main",
        "git pull",
    ]
