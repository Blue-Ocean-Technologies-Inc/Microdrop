# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""source_update_startup: the startup step moves a managed checkout to the
newest release by the user's preference and re-runs the app — against real
git repositories, with the re-run, the preference, and the sleeps faked."""

# Standard library imports.
import logging
import os
import shutil
import sys
from collections import namedtuple
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils import source_update_startup
from microdrop_utils.source_update_startup import (
    AUTO_UPDATE_PREFERENCE_PATH,
    SKIP_GIT_UPDATE_ENV_VAR,
    UPDATE_APPLIED_ENV_VAR,
    apply_source_update_policy,
    skip_variable_is_set,
    source_version_line,
)
from microdrop_utils.source_version import SourceVersionError, exact_release
from microdrop_utils.tests.git_repo_fixtures import run_git

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)

#: The real restart, before the autouse fixture replaces it.
ORIGINAL_RESTART_APP = source_update_startup._restart_app

#: One faked re-run of the app.
RerunCall = namedtuple("RerunCall", "argv env")


def _head(repo):
    return run_git(repo, "rev-parse", "HEAD").stdout.strip()


class FakeChild:
    """A Popen stand-in that records every call made on it; its ``wait``
    answers ``waits`` in turn — an exception to raise, or an exit code."""

    def __init__(self, *waits):
        self.waits = list(waits)
        self.calls = []
        self.returncode = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.calls.append("exit")

    def wait(self):
        self.calls.append("wait")
        answer = self.waits.pop(0)

        if isinstance(answer, BaseException):
            raise answer

        self.returncode = answer

        return answer

    def kill(self):
        self.calls.append("kill")

    def terminate(self):
        self.calls.append("terminate")


#: Stands in for the updates preferences file; the step must ask for it.
UPDATES_PREFERENCES_FILE = Path("app-home") / "app_updates.ini"


@pytest.fixture(autouse=True)
def calls(monkeypatch):
    """The restarts the step started; none ever starts a real process.

    Also clears both variables (this machine may set them, in its process or
    persisted for the user), answers the auto-update preference with its
    default without locating or reading the real file, and makes the retry
    sleeps instant."""
    recorded = []

    def fake_restart(argv, env):
        recorded.append(RerunCall(argv, env))

        raise SystemExit(7)

    monkeypatch.delenv(SKIP_GIT_UPDATE_ENV_VAR, raising=False)
    monkeypatch.delenv(UPDATE_APPLIED_ENV_VAR, raising=False)
    monkeypatch.setattr(
        source_update_startup, "user_environment_variable", lambda name: None
    )
    monkeypatch.setattr(
        source_update_startup,
        "updates_preferences_file_path",
        lambda: UPDATES_PREFERENCES_FILE,
    )
    monkeypatch.setattr(
        source_update_startup,
        "read_bool_preference",
        lambda path, default, filename=None: default,
    )
    monkeypatch.setattr(source_update_startup, "_restart_app", fake_restart)
    monkeypatch.setattr(source_update_startup.time, "sleep", lambda seconds: None)

    return recorded


@pytest.fixture
def real_restart(monkeypatch):
    """Undo the fixture's fake restart; exec and Popen are the test's to fake,
    and spawning refuses outright unless the test replaces it."""
    monkeypatch.setattr(source_update_startup, "_restart_app", ORIGINAL_RESTART_APP)

    def refuse_spawn(*args, **kwargs):
        raise AssertionError("the restart spawned a process")

    monkeypatch.setattr(source_update_startup.subprocess, "Popen", refuse_spawn)
    monkeypatch.setattr(source_update_startup.os, "execve", refuse_spawn)


def test_stay_policy_never_moves_the_checkout(clone_at_v1_2, monkeypatch, calls):
    reads = []

    def stay(path, default, filename=None):
        reads.append((path, filename))

        return False

    monkeypatch.setattr(source_update_startup, "read_bool_preference", stay)
    head = _head(clone_at_v1_2)

    apply_source_update_policy(clone_at_v1_2)

    # The policy has a file of its own, never the app's preferences.ini.
    assert reads == [(AUTO_UPDATE_PREFERENCE_PATH, UPDATES_PREFERENCES_FILE)]
    assert _head(clone_at_v1_2) == head
    assert calls == []


def test_latest_policy_switches_and_reruns(clone_at_v1_2, calls):
    with pytest.raises(SystemExit) as exit_info:
        apply_source_update_policy(clone_at_v1_2)

    assert exit_info.value.code == 7
    assert exact_release(clone_at_v1_2) == "v1.10.0"
    assert len(calls) == 1
    assert calls[0].argv == [sys.executable, *sys.orig_argv[1:]]
    assert calls[0].env[UPDATE_APPLIED_ENV_VAR] == "1"


def test_child_does_not_apply_again(clone_at_v1_2, monkeypatch, calls):
    monkeypatch.setenv(UPDATE_APPLIED_ENV_VAR, "1")
    head = _head(clone_at_v1_2)

    apply_source_update_policy(clone_at_v1_2)

    assert _head(clone_at_v1_2) == head
    assert calls == []
    # Whatever the re-run starts later (the in-app relaunch) updates again.
    assert UPDATE_APPLIED_ENV_VAR not in os.environ


def test_skip_variable_stops_the_update(clone_at_v1_2, monkeypatch, calls, caplog):
    monkeypatch.setenv(SKIP_GIT_UPDATE_ENV_VAR, "1")
    head = _head(clone_at_v1_2)

    with caplog.at_level(logging.INFO, logger=source_update_startup.__name__):
        apply_source_update_policy(clone_at_v1_2)

    assert _head(clone_at_v1_2) == head
    assert calls == []
    assert SKIP_GIT_UPDATE_ENV_VAR in caplog.text


def test_persisted_skip_variable_stops_the_update(clone_at_v1_2, monkeypatch, calls):
    # Saved for the user after this process started: its environment is stale.
    persisted = {SKIP_GIT_UPDATE_ENV_VAR: "1"}

    monkeypatch.setattr(
        source_update_startup, "user_environment_variable", persisted.get
    )
    head = _head(clone_at_v1_2)

    apply_source_update_policy(clone_at_v1_2)

    assert _head(clone_at_v1_2) == head
    assert calls == []


def test_skip_variable_is_set_reads_process_and_user_environment(monkeypatch):
    persisted = {}

    monkeypatch.setattr(
        source_update_startup, "user_environment_variable", persisted.get
    )

    assert skip_variable_is_set() is False

    monkeypatch.setenv(SKIP_GIT_UPDATE_ENV_VAR, "1")

    assert skip_variable_is_set() is True

    monkeypatch.delenv(SKIP_GIT_UPDATE_ENV_VAR)
    persisted[SKIP_GIT_UPDATE_ENV_VAR] = "1"

    assert skip_variable_is_set() is True


def test_applied_variable_is_dropped_when_the_version_line_fails(monkeypatch, calls):
    def broken(repo_root):
        raise RuntimeError("describe failed")

    monkeypatch.setenv(UPDATE_APPLIED_ENV_VAR, "1")
    monkeypatch.setattr(source_update_startup, "source_version_line", broken)

    apply_source_update_policy()

    assert UPDATE_APPLIED_ENV_VAR not in os.environ
    assert calls == []


def test_development_checkout_is_left_alone(clone, calls):
    run_git(clone, "checkout", "-b", "feat/x", "v1.2.0")
    head = _head(clone)

    apply_source_update_policy(clone)

    assert _head(clone) == head
    assert calls == []


def test_up_to_date_checkout_does_nothing(clone, calls):
    head = _head(clone)

    apply_source_update_policy(clone)

    assert _head(clone) == head
    assert calls == []


def _refuse_checkout(monkeypatch, output):
    """Make every checkout fail with git printing ``output``; return the
    list of attempts and the list of sleeps between them."""
    attempts = []
    sleeps = []

    def refuse(repo_root, tag_name):
        attempts.append(tag_name)

        raise SourceVersionError("`git checkout` exited with code 1", output)

    monkeypatch.setattr(source_update_startup, "switch_to", refuse)
    monkeypatch.setattr(source_update_startup.time, "sleep", sleeps.append)

    return attempts, sleeps


def test_checkout_blocked_by_the_index_lock_is_retried(
    clone_at_v1_2, monkeypatch, calls, caplog
):
    lock_message = "fatal: Unable to create '.git/index.lock': File exists."
    attempts, sleeps = _refuse_checkout(monkeypatch, lock_message)

    with caplog.at_level(logging.WARNING, logger=source_update_startup.__name__):
        apply_source_update_policy(clone_at_v1_2)

    assert exact_release(clone_at_v1_2) == "v1.2.0"
    assert calls == []
    assert len(attempts) == source_update_startup.CHECKOUT_RETRY_COUNT + 1
    assert len(sleeps) == source_update_startup.CHECKOUT_RETRY_COUNT
    assert "index.lock" in caplog.text


def test_checkout_refused_for_another_reason_warns_once_without_waiting(
    clone_at_v1_2, monkeypatch, calls, caplog
):
    in_the_way = "error: untracked working tree files would be overwritten"
    attempts, sleeps = _refuse_checkout(monkeypatch, in_the_way)

    with caplog.at_level(logging.WARNING, logger=source_update_startup.__name__):
        apply_source_update_policy(clone_at_v1_2)

    assert exact_release(clone_at_v1_2) == "v1.2.0"
    assert calls == []
    assert attempts == ["v1.10.0"]
    assert sleeps == []
    assert caplog.text.count("Could not switch the MicroDrop source") == 1
    assert "would be overwritten" in caplog.text


def test_checkout_lost_to_another_process_counts_as_switched(
    clone_at_v1_2, monkeypatch, calls
):
    def switched_elsewhere(repo_root, tag_name):
        run_git(repo_root, "checkout", "--detach", tag_name)

        raise SourceVersionError("`git checkout` exited with code 1", "index.lock")

    monkeypatch.setattr(source_update_startup, "switch_to", switched_elsewhere)

    with pytest.raises(SystemExit):
        apply_source_update_policy(clone_at_v1_2)

    assert exact_release(clone_at_v1_2) == "v1.10.0"
    assert len(calls) == 1


def test_failed_restart_warns_and_continues_on_the_new_tag(
    clone_at_v1_2, monkeypatch, calls, caplog
):
    def cannot_start(argv, env):
        raise OSError("no such interpreter")

    monkeypatch.setattr(source_update_startup, "_restart_app", cannot_start)

    with caplog.at_level(logging.WARNING, logger=source_update_startup.__name__):
        assert apply_source_update_policy(clone_at_v1_2) is None

    assert exact_release(clone_at_v1_2) == "v1.10.0"
    assert "now on v1.10.0" in caplog.text
    assert "no such interpreter" in caplog.text
    assert "restart MicroDrop" in caplog.text


def test_unexpected_restart_error_still_says_the_source_moved(
    clone_at_v1_2, monkeypatch, calls, caplog
):
    def broken(argv, env):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(source_update_startup, "_restart_app", broken)

    with caplog.at_level(logging.WARNING, logger=source_update_startup.__name__):
        assert apply_source_update_policy(clone_at_v1_2) is None

    assert exact_release(clone_at_v1_2) == "v1.10.0"
    assert "now on v1.10.0" in caplog.text
    assert "restart MicroDrop" in caplog.text
    assert "Source update at startup failed" not in caplog.text


def test_unexpected_error_never_escapes(monkeypatch, tmp_path, calls, caplog):
    def broken(repo_root):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(source_update_startup, "pending_update", broken)

    with caplog.at_level(logging.WARNING, logger=source_update_startup.__name__):
        assert apply_source_update_policy(tmp_path) is None

    assert calls == []
    assert "unexpected" in caplog.text


def _restart_env():
    return {**os.environ, UPDATE_APPLIED_ENV_VAR: "1"}


def test_posix_restart_replaces_the_process(monkeypatch, real_restart):
    execs = []

    monkeypatch.setattr(source_update_startup, "_is_posix", lambda: True)
    monkeypatch.setattr(
        source_update_startup.os, "execve", lambda *args: execs.append(args)
    )

    source_update_startup._rerun_and_exit()

    assert execs == [
        (sys.executable, [sys.executable, *sys.orig_argv[1:]], _restart_env())
    ]


def test_posix_restart_failure_raises(monkeypatch, real_restart):
    def cannot_exec(*args):
        raise OSError("exec format error")

    monkeypatch.setattr(source_update_startup, "_is_posix", lambda: True)
    monkeypatch.setattr(source_update_startup.os, "execve", cannot_exec)

    with pytest.raises(OSError):
        source_update_startup._rerun_and_exit()


def _spawn(monkeypatch, child):
    """Make the Windows restart spawn ``child``; return the spawn records."""
    spawns = []

    def fake_popen(argv, env=None):
        spawns.append(RerunCall(argv, env))

        return child

    monkeypatch.setattr(source_update_startup, "_is_posix", lambda: False)
    monkeypatch.setattr(source_update_startup.subprocess, "Popen", fake_popen)

    return spawns


def test_windows_restart_exits_with_the_child_code(monkeypatch, real_restart):
    child = FakeChild(3)
    spawns = _spawn(monkeypatch, child)

    with pytest.raises(SystemExit) as exit_info:
        source_update_startup._rerun_and_exit()

    assert exit_info.value.code == 3
    assert spawns == [RerunCall([sys.executable, *sys.orig_argv[1:]], _restart_env())]
    assert child.calls == ["wait", "exit"]


def test_windows_restart_outlives_ctrl_c(monkeypatch, real_restart):
    child = FakeChild(KeyboardInterrupt(), 3)
    _spawn(monkeypatch, child)

    with pytest.raises(SystemExit) as exit_info:
        source_update_startup._rerun_and_exit()

    assert exit_info.value.code == 3
    # Never killed: the child got the same Ctrl+C and is shutting down.
    assert child.calls == ["wait", "wait", "exit"]


def test_version_line_for_branch_pinned_and_no_git(clone, tmp_path):
    assert source_version_line(clone).startswith(
        "MicroDrop source version: v1.10.0-1-g"
    )
    assert source_version_line(clone).endswith(" (main)")

    run_git(clone, "checkout", "--detach", "v1.2.0")

    assert source_version_line(clone) == (
        "MicroDrop source version: v1.2.0 (pinned release)"
    )
    assert source_version_line(tmp_path) == (
        "MicroDrop source version: unknown (not a git checkout)"
    )


def test_worker_process_does_nothing(monkeypatch, calls):
    def never(repo_root):
        raise AssertionError("a worker process must not read the checkout")

    monkeypatch.setattr(
        source_update_startup.multiprocessing, "parent_process", lambda: object()
    )
    monkeypatch.setattr(source_update_startup, "source_version_line", never)
    monkeypatch.setattr(source_update_startup, "checkout_state", never)

    assert apply_source_update_policy() is None
    assert calls == []
