# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""COM-free tests for the DirectShow thread runner in
``directshow_camera_controls``: plain callables stand in for COM calls, and
the thread's COM initialisation is stubbed out, so they run on any OS.
"""

# Standard library imports.
import threading

# Third-party imports.
import pytest

# Microdrop utils imports.
import microdrop_utils.directshow_camera_controls as directshow
from microdrop_utils.directshow_camera_controls import DirectShowStallError

#: Seconds a test waits for a released call to return.
RELEASE_WAIT_S = 2


@pytest.fixture(autouse=True)
def fresh_runner(monkeypatch):
    """Give each test its own runner state and a tiny timeout; yield a
    list collecting the events that hold calls blocked, all set (releasing
    the daemon threads) at teardown."""
    monkeypatch.setattr(directshow, "DIRECTSHOW_CALL_TIMEOUT_S", 0.05)
    monkeypatch.setattr(directshow, "_initialize_com_apartment", lambda: None)
    monkeypatch.setattr(directshow, "_com_jobs", None)
    monkeypatch.setattr(directshow, "_stalled_call", None)
    monkeypatch.setattr(directshow, "_abandoned_calls", [])

    releases = []

    yield releases

    for release in releases:
        release.set()


def _stall(releases):
    """Run a call that blocks until released; return its release event."""
    release = threading.Event()
    releases.append(release)

    with pytest.raises(DirectShowStallError):
        directshow._run_on_com_thread(release.wait)

    return release


def test_result_returned():
    assert directshow._run_on_com_thread(lambda a, b: a + b, 2, 3) == 5


def test_calls_run_on_one_dedicated_thread():
    first = directshow._run_on_com_thread(threading.get_ident)
    second = directshow._run_on_com_thread(threading.get_ident)

    assert first == second != threading.get_ident()


def test_exception_propagated():
    def fail():
        raise ValueError("rejected value")

    with pytest.raises(ValueError, match="rejected value"):
        directshow._run_on_com_thread(fail)


def test_blocking_call_times_out(fresh_runner):
    _stall(fresh_runner)

    assert directshow._com_thread_stalled()


def test_call_fails_fast_while_stalled(fresh_runner):
    _stall(fresh_runner)
    ran = threading.Event()

    with pytest.raises(DirectShowStallError):
        directshow._run_on_com_thread(ran.set)

    # Never queued, so it cannot run once the stall clears either.
    assert not ran.wait(0.2)


def test_recovers_once_stalled_call_returns(fresh_runner):
    release = _stall(fresh_runner)
    stalled_call = directshow._stalled_call[0]

    release.set()
    stalled_call.result(timeout=RELEASE_WAIT_S)

    assert directshow._run_on_com_thread(lambda: "ok") == "ok"


def test_retry_runs_on_fresh_thread_while_old_call_blocks(fresh_runner):
    _stall(fresh_runner)
    stalled_call = directshow._stalled_call[0]

    directshow._retry_stalled_com_thread()

    assert directshow._run_on_com_thread(lambda: "ok") == "ok"
    assert not stalled_call.done()


def test_retry_without_stall_keeps_thread():
    thread_id = directshow._run_on_com_thread(threading.get_ident)

    directshow._retry_stalled_com_thread()

    assert directshow._run_on_com_thread(threading.get_ident) == thread_id


def test_retry_cap_enforced(fresh_runner):
    for _abandoned in range(directshow.DIRECTSHOW_MAX_ABANDONED_THREADS):
        _stall(fresh_runner)
        directshow._retry_stalled_com_thread()

    _stall(fresh_runner)

    with pytest.raises(DirectShowStallError) as raised:
        directshow._retry_stalled_com_thread()

    assert raised.value.retry_exhausted

    with pytest.raises(DirectShowStallError):
        directshow._run_on_com_thread(lambda: "ok")


def test_retry_allowed_again_once_abandoned_call_returns(fresh_runner):
    for _abandoned in range(directshow.DIRECTSHOW_MAX_ABANDONED_THREADS):
        _stall(fresh_runner)
        directshow._retry_stalled_com_thread()

    _stall(fresh_runner)
    first_abandoned = directshow._abandoned_calls[0]

    fresh_runner[0].set()
    first_abandoned.result(timeout=RELEASE_WAIT_S)
    directshow._retry_stalled_com_thread()

    assert directshow._run_on_com_thread(lambda: "ok") == "ok"


# --- _run_on_com_thread_async ----------------------------------------------------


class _Outcomes:
    """An on_done callback recording every (result, error) it gets."""

    def __init__(self):
        self.calls = []
        self.reported = threading.Event()

    def __call__(self, result, error):
        self.calls.append((result, error))
        self.reported.set()

    def wait(self):
        assert self.reported.wait(RELEASE_WAIT_S)

        return self.calls[0]


def _run_async(function, *args):
    """Start ``function(*args)`` asynchronously; return its _Outcomes."""
    outcomes = _Outcomes()
    progress = {"step": "testing"}

    directshow._run_on_com_thread_async(function, args, progress, outcomes)

    return outcomes


def test_async_result_reported_once():
    outcomes = _run_async(lambda a, b: a + b, 2, 3)

    assert outcomes.wait() == (5, None)

    # Past the timeout, the cancelled watchdog reports nothing more.
    threading.Event().wait(0.2)
    assert len(outcomes.calls) == 1


def test_async_exception_reported():
    def fail():
        raise ValueError("rejected value")

    _result, error = _run_async(fail).wait()

    assert isinstance(error, ValueError)


def test_async_stall_reported_without_blocking_the_caller(fresh_runner):
    release = threading.Event()
    fresh_runner.append(release)

    outcomes = _run_async(release.wait)

    # The call is still blocked, yet the caller is already back.
    assert not outcomes.calls

    result, error = outcomes.wait()

    assert result is None
    assert isinstance(error, DirectShowStallError)
    assert error.step == "testing"
    assert directshow._com_thread_stalled()

    # The late return is dropped.
    stalled_call = directshow._stalled_call[0]
    release.set()
    stalled_call.result(timeout=RELEASE_WAIT_S)

    # Done callbacks run just after result() wakes up.
    threading.Event().wait(0.1)
    assert len(outcomes.calls) == 1


def test_async_call_retries_on_fresh_thread_after_stall(fresh_runner):
    _stall(fresh_runner)
    stalled_call = directshow._stalled_call[0]

    assert _run_async(lambda: "ok").wait() == ("ok", None)
    assert not stalled_call.done()


def test_async_call_refused_once_retry_cap_reached(fresh_runner):
    for _abandoned in range(directshow.DIRECTSHOW_MAX_ABANDONED_THREADS):
        _stall(fresh_runner)
        directshow._retry_stalled_com_thread()

    _stall(fresh_runner)

    result, error = _run_async(lambda: "ok").wait()

    assert result is None
    assert error.retry_exhausted
