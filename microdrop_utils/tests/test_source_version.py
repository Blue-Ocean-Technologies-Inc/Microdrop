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
from microdrop_utils import source_version
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
    current_release,
    describe,
    exact_release,
    fetch_tags,
    is_newer_release,
    list_release_tags,
    parse_release,
    pending_update,
    return_commands,
    switch_to,
)
from microdrop_utils.tests.git_repo_fixtures import clone_repo, run_git

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)


def _fail_git_command(monkeypatch, subcommand, failure):
    """Make the module's ``git <subcommand>`` fail with ``failure`` — a
    CompletedProcess to answer, or an exception to raise; every other git
    command still runs."""
    real_git = source_version._git

    def fake_git(repo_root, *args, **kwargs):
        if args[0] != subcommand:
            return real_git(repo_root, *args, **kwargs)

        if isinstance(failure, Exception):
            raise failure

        return failure

    monkeypatch.setattr(source_version, "_git", fake_git)


def test_parse_release_accepts_only_three_part_versions():
    assert parse_release("v1.46.0") == (1, 46, 0)
    assert parse_release("v2.0.0rc1") is None
    assert parse_release("nightly") is None
    assert parse_release("v1.46") is None


def test_is_newer_release_compares_versions_and_treats_no_release_as_oldest():
    assert is_newer_release("v1.10.0", "v1.2.0") is True
    assert is_newer_release("v1.2.0", "v1.10.0") is False
    assert is_newer_release("v1.10.0", "v1.10.0") is False
    # A checkout built on no release is older than any.
    assert is_newer_release("v0.0.1", None) is True
    assert is_newer_release("v0.0.1", "") is True
    assert is_newer_release("nightly", "v1.2.0") is False


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


def _commit_off_main(repo):
    """Commit on a new branch ``feat/x`` off ``main`` and stay on it."""
    run_git(repo, "checkout", "-b", "feat/x")
    (repo / "feature.txt").write_text("feature work\n")
    run_git(repo, "add", "feature.txt")
    run_git(repo, "commit", "-m", "feat: work not on main")


def test_state_managed_on_main_and_when_detached_at_a_release(clone):
    assert checkout_state(clone) == (MANAGED, "")
    assert current_branch(clone) == "main"

    run_git(clone, "checkout", "--detach", "v1.2.0")

    assert checkout_state(clone) == (MANAGED, "")
    assert current_branch(clone) == ""


def test_state_managed_detached_at_an_untagged_commit_on_origin_main(clone):
    # Where the launcher pins a fresh install: on main, between releases.
    run_git(clone, "checkout", "--detach", "HEAD")

    assert exact_release(clone) is None
    assert checkout_state(clone) == (MANAGED, "")


def test_state_managed_detached_at_a_release_tag_off_main(clone):
    _commit_off_main(clone)
    run_git(clone, "tag", "v1.11.0")
    run_git(clone, "checkout", "--detach", "v1.11.0")

    assert checkout_state(clone) == (MANAGED, "")


def test_state_development_detached_at_a_commit_not_on_main(clone):
    _commit_off_main(clone)
    run_git(clone, "checkout", "--detach", "feat/x")

    assert checkout_state(clone) == (
        DEVELOPMENT,
        "detached at a commit that is not on main",
    )


def test_state_without_origin_main_only_a_release_tag_is_managed(clone):
    run_git(clone, "remote", "remove", "origin")
    run_git(clone, "checkout", "--detach", "HEAD")

    assert checkout_state(clone) == (
        DEVELOPMENT,
        "detached at a commit that is not on main",
    )

    run_git(clone, "checkout", "--detach", "v1.2.0")

    assert checkout_state(clone) == (MANAGED, "")


def test_state_development_while_bisecting(clone):
    # Bisecting detaches HEAD at commits on main, release tags among them.
    run_git(clone, "bisect", "start", "HEAD", "v1.0.0")

    assert current_branch(clone) == ""
    assert checkout_state(clone) == (DEVELOPMENT, "git operation in progress")

    run_git(clone, "bisect", "reset")

    assert checkout_state(clone) == (MANAGED, "")


def test_state_development_while_rebasing(clone):
    run_git(clone, "checkout", "--detach", "v1.2.0")

    # The exec step fails, so the rebase stops half way.
    stopped = subprocess.run(
        ["git", "rebase", "--force-rebase", "--exec", "false", "v1.1.0"],
        cwd=str(clone),
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )

    assert stopped.returncode != 0
    assert (clone / ".git" / "rebase-merge").is_dir()
    assert checkout_state(clone) == (DEVELOPMENT, "git operation in progress")


def test_state_no_git_when_the_operation_check_fails(clone, monkeypatch):
    failure = subprocess.CompletedProcess(["git", "rev-parse"], 128, "", "fatal\n")
    _fail_git_command(monkeypatch, "rev-parse", failure)

    assert checkout_state(clone)[0] == NO_GIT


def test_a_worktree_checkout_with_a_dot_git_file(clone, tmp_path):
    # The real install is a submodule, whose .git is a file, as here.
    worktree = tmp_path / "worktree"

    run_git(clone, "worktree", "add", "--detach", str(worktree), "v1.2.0")

    assert (worktree / ".git").is_file()
    assert checkout_state(worktree) == (MANAGED, "")
    assert [t.name for t in list_release_tags(worktree)] == [
        "v1.10.0",
        "v1.2.0",
        "v1.1.0",
        "v1.0.0",
    ]
    assert pending_update(worktree).name == "v1.10.0"

    # Its operation files live in the main repository's .git/worktrees/.
    run_git(worktree, "bisect", "start", "HEAD", "v1.0.0")

    assert checkout_state(worktree) == (DEVELOPMENT, "git operation in progress")
    assert checkout_state(clone) == (MANAGED, "")


def test_state_development_on_feature_branch(clone):
    run_git(clone, "checkout", "-b", "feat/x")

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


def test_state_no_git_when_git_status_fails(clone, monkeypatch):
    failure = subprocess.CompletedProcess(
        ["git", "status"], 128, "", "fatal: detected dubious ownership\n"
    )
    _fail_git_command(monkeypatch, "status", failure)

    assert checkout_state(clone) == (
        NO_GIT,
        "git status failed: fatal: detected dubious ownership",
    )


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess(["git", "symbolic-ref"], 128, "", "fatal: bad\n"),
        SourceVersionError("`git symbolic-ref` could not run: timed out"),
    ],
    ids=["exit-code", "timeout"],
)
def test_state_no_git_when_the_branch_cannot_be_read(clone, monkeypatch, failure):
    # On a feature branch, so a failed read passing for "detached" would
    # misreport the checkout as managed.
    run_git(clone, "checkout", "-b", "feat/x")
    _fail_git_command(monkeypatch, "symbolic-ref", failure)

    assert checkout_state(clone)[0] == NO_GIT


def test_current_release_is_the_newest_reachable_release(clone):
    assert current_release(clone) == "v1.10.0"

    run_git(clone, "checkout", "--detach", "v1.2.0")

    assert current_release(clone) == "v1.2.0"


def test_near_miss_tags_never_count_as_releases(clone):
    run_git(clone, "tag", "v1.47")
    run_git(clone, "tag", "v1.2.3.4")

    assert current_release(clone) == "v1.10.0"
    assert exact_release(clone) is None
    assert pending_update(clone) is None


def test_exact_release_at_and_off_a_tag(clone):
    assert exact_release(clone) is None

    run_git(clone, "checkout", "--detach", "v1.10.0")

    assert exact_release(clone) == "v1.10.0"


def test_a_branch_named_like_a_tag_does_not_hide_it(clone):
    run_git(clone, "branch", "v1.2.0")

    assert "v1.2.0" in [t.name for t in list_release_tags(clone)]


def test_pending_update_is_none_when_ahead_of_newest_tag(clone):
    assert describe(clone).startswith("v1.10.0-1-g")
    assert pending_update(clone) is None


def test_pending_update_from_older_tag(clone):
    run_git(clone, "checkout", "--detach", "v1.2.0")

    assert pending_update(clone).name == "v1.10.0"


def test_pending_update_skips_tags_without_the_panel(clone):
    run_git(clone, "tag", "-d", "v1.2.0", "v1.10.0")
    run_git(clone, "checkout", "--detach", "v1.0.0")

    assert pending_update(clone) is None


def test_pending_update_is_none_on_development_checkout(clone):
    run_git(clone, "checkout", "--detach", "v1.2.0")
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
    publisher = clone_repo(source_repo, tmp_path / "publisher")

    run_git(publisher, "tag", "v1.11.0")

    assert "v1.11.0" not in [t.name for t in list_release_tags(clone)]

    run_git(publisher, "push", "origin", "v1.11.0")

    try:
        fetch_tags(clone)
    finally:
        # The source repository is shared by the whole module.
        run_git(source_repo, "tag", "-d", "v1.11.0")

    assert list_release_tags(clone)[0].name == "v1.11.0"


def test_fetch_tags_has_its_own_timeout_and_ends_a_stalled_transfer(
    tmp_path, monkeypatch
):
    runs = []

    def fake_run(argv, **kwargs):
        runs.append((argv, kwargs["timeout"]))

        return subprocess.CompletedProcess(argv, 0, "", "")

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(source_version.subprocess, "run", fake_run)

    fetch_tags(tmp_path)

    assert runs == [
        (
            [
                "git",
                "-c",
                "http.lowSpeedLimit=1000",
                "-c",
                "http.lowSpeedTime=30",
                "fetch",
                "--tags",
                "--quiet",
                "origin",
            ],
            source_version.FETCH_TIMEOUT_S,
        )
    ]
    assert source_version.FETCH_TIMEOUT_S == 120


def test_fetch_tags_raises_without_remote(clone):
    run_git(clone, "remote", "remove", "origin")

    with pytest.raises(SourceVersionError) as raised:
        fetch_tags(clone)

    assert raised.value.output


def test_list_release_tags_empty_in_repo_without_tags(tmp_path):
    run_git(tmp_path, "init", "-b", "main")

    assert list_release_tags(tmp_path) == []


def test_return_commands(tmp_path):
    assert return_commands(tmp_path).splitlines() == [
        f'cd "{tmp_path}"',
        "git checkout main",
        "git pull",
    ]
