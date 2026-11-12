# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for ProtocolAutosaveModel's debounce and write decisions (#966).

Qt-free: the model takes ``now`` explicitly, so a plain float is the clock.
"""

# Microdrop package imports.
from pluggable_protocol_tree.models.protocol_autosave import ProtocolAutosaveModel
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)

DEBOUNCE_S = 1.5


def _model(enabled=True, path="C:/protocols/p.json", modified=True):
    tracker = PluggableProtocolStateTracker(
        loaded_protocol_path=path, is_modified=modified
    )

    return ProtocolAutosaveModel(
        tracker=tracker, enabled=enabled, debounce_s=DEBOUNCE_S
    )


def test_change_is_due_only_after_the_quiet_period():
    model = _model()

    model.note_change(10.0)

    assert model.seconds_until_due(10.0) == DEBOUNCE_S
    assert not model.claim_due_save(11.0)
    assert model.claim_due_save(10.0 + DEBOUNCE_S)


def test_a_new_change_restarts_the_debounce():
    model = _model()

    model.note_change(10.0)
    model.note_change(11.0)

    assert not model.claim_due_save(10.0 + DEBOUNCE_S)
    assert model.claim_due_save(11.0 + DEBOUNCE_S)


def test_a_claimed_save_is_consumed():
    model = _model()
    model.note_change(0.0)

    assert model.claim_due_save(DEBOUNCE_S)
    assert not model.claim_due_save(DEBOUNCE_S + 1)
    assert model.seconds_until_due(DEBOUNCE_S + 1) is None


def test_off_never_schedules_or_writes():
    model = _model(enabled=False)

    model.note_change(0.0)

    assert model.seconds_until_due(0.0) is None
    assert not model.claim_due_save(100.0)
    assert not model.claim_flush_save()


def test_never_saved_protocol_is_not_written():
    model = _model(path="")
    model.note_change(0.0)

    assert not model.has_target
    assert not model.claim_due_save(DEBOUNCE_S)
    assert model.label_text == "AutoSave: On (no file)"
    assert "save the protocol once" in model.status_text


def test_first_save_as_gives_autosave_a_target():
    model = _model(path="")

    model.tracker.loaded_protocol_path = "C:/protocols/new.json"
    model.note_change(0.0)

    assert model.claim_due_save(DEBOUNCE_S)
    assert model.label_text == "AutoSave: On"


def test_clean_protocol_is_not_rewritten():
    model = _model(modified=False)
    model.note_change(0.0)

    assert not model.claim_due_save(DEBOUNCE_S)


def test_run_holds_the_write_until_it_ends():
    model = _model()
    model.tracker.is_active = True
    model.note_change(0.0)

    assert not model.claim_due_save(DEBOUNCE_S)
    assert model.seconds_until_due(DEBOUNCE_S) == 0.0

    model.tracker.is_active = False
    model.note_run_ended(5.0)

    assert model.claim_due_save(5.0)


def test_run_end_without_changes_writes_nothing():
    model = _model(modified=False)

    model.note_run_ended(5.0)

    assert model.seconds_until_due(5.0) is None


def test_flush_writes_pending_changes_immediately():
    model = _model()
    model.note_change(0.0)

    assert model.claim_flush_save()
    assert model.seconds_until_due(0.0) is None


def test_flush_waits_for_a_running_protocol():
    model = _model()
    model.tracker.is_active = True

    assert not model.claim_flush_save()


def test_failure_is_reported_once_until_the_protocol_is_clean():
    model = _model()

    assert model.record_save_failed("disk full")
    assert not model.record_save_failed("disk full")
    assert model.label_text == "AutoSave: Failed"
    assert "disk full" in model.status_text

    model.tracker.is_modified = False

    assert model.last_error == ""
    assert model.label_text == "AutoSave: On"

    model.tracker.is_modified = True

    assert model.record_save_failed("disk full")


def test_off_label_and_tooltip():
    model = _model(enabled=False)

    assert model.label_text == "AutoSave: Off"
    assert "off" in model.status_text
