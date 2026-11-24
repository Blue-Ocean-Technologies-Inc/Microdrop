# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The plugin load records and their aggregate state."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import (
    LOAD_FAILED,
    LOAD_LOADED,
    LOAD_LOADING,
    LOAD_PENDING,
    PluginLoadStatus,
    summarize_exception,
)

A = SimpleNamespace(id="a.plugin", name="A Plugin")
B = SimpleNamespace(id="b.plugin", name="B Plugin")


def _start(status, plugin, error=None):
    """Run a fake start of ``plugin`` inside the recording block."""
    with status.recording(plugin):
        if error is not None:
            raise error


def test_empty_status_counts_as_loaded():
    status = PluginLoadStatus()

    assert status.state == LOAD_LOADED
    assert status.summary == "0 plugins loaded"


def test_pending_records_keep_load_order_and_make_the_state_loading():
    status = PluginLoadStatus()
    status.mark_pending(A.id, A.name, essential=True)
    status.mark_pending(B.id, B.name)

    assert [record.plugin_id for record in status.records] == [A.id, B.id]
    assert status.get_record(A.id).essential is True
    assert status.state == LOAD_LOADING
    assert status.loading_count == 2


def test_recording_moves_a_record_to_loaded_with_its_duration():
    status = PluginLoadStatus()
    status.mark_pending(A.id, A.name)

    with status.recording(A) as record:
        assert record.state == LOAD_LOADING

    assert record.state == LOAD_LOADED
    assert record.duration >= 0
    assert status.state == LOAD_LOADED
    assert status.summary == "1 plugins loaded"


def test_a_failed_start_is_recorded_with_its_traceback_and_propagates():
    status = PluginLoadStatus()

    with pytest.raises(RuntimeError):
        _start(status, A, RuntimeError("no device\nsecond line"))

    record = status.get_record(A.id)

    assert record.state == LOAD_FAILED
    assert record.error == "RuntimeError: no device"
    assert "Traceback" in record.traceback
    assert "no device" in record.traceback


def test_failed_wins_over_loaded_but_loading_wins_over_both():
    status = PluginLoadStatus()
    _start(status, A)

    with pytest.raises(ValueError):
        _start(status, B, ValueError("bad"))

    assert status.state == LOAD_FAILED
    assert (status.loaded_count, status.failed_count) == (1, 1)
    assert status.summary == "1 plugins loaded, 1 failed"

    status.mark_pending("c.plugin")

    assert status.state == LOAD_LOADING
    assert status.summary == "1 plugins loaded, 1 loading, 1 failed"


def test_state_change_notifies_observers():
    status = PluginLoadStatus()
    seen = []
    status.observe(lambda event: seen.append(status.state), "state")

    status.mark_pending(A.id)
    _start(status, A)

    assert seen[0] == LOAD_LOADING
    assert seen[-1] == LOAD_LOADED


def test_a_retried_plugin_reuses_its_record():
    status = PluginLoadStatus()

    with pytest.raises(RuntimeError):
        _start(status, A, RuntimeError("first"))

    _start(status, A)

    assert len(status.records) == 1
    assert status.get_record(A.id).state == LOAD_LOADED
    assert status.get_record(A.id).traceback == ""


def test_discard_drops_the_record():
    status = PluginLoadStatus()
    status.mark_failed(A.id, "ImportError: x", "Traceback ...")
    status.discard(A.id)
    status.discard("never.recorded")

    assert status.records == []


def test_mark_failed_adds_an_unknown_plugin():
    status = PluginLoadStatus()
    status.mark_failed("pkg.mod:Cls", "ImportError: x", "Traceback ...")

    record = status.get_record("pkg.mod:Cls")

    assert record.state == LOAD_FAILED
    assert record.name == "pkg.mod:Cls"
    assert record.state != LOAD_PENDING


def test_summarize_exception_without_a_message():
    assert summarize_exception(KeyError()) == "KeyError"
