# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The hub model's run tracking: run_id filtering, the run lifecycle, the
preflight resync and the backend-owned unsaved calibration."""

# Third-party imports.
import pytest

# Local imports.
from ..consts import (
    PREFLIGHT_BOARD_BUSY_ERROR,
    UNSAVED_CALIBRATION,
    UNSAVED_TARE,
    SelfTestCalibrationSaved,
    SelfTestFinished,
    SelfTestPreflight,
    SelfTestProgress,
    SelfTestResult,
    SelfTestRunRequest,
)
from ..models.consts import (
    CHANNELS_TEST,
    OUTCOME_FAIL,
    OUTCOME_NOT_RUN,
    OUTCOME_PASS,
    OUTCOME_QUEUED,
    OUTCOME_RUNNING,
    PREFLIGHT_DISCONNECTED_ERROR,
    VOLTAGE_TEST,
)
from ..models.self_tests_model import SelfTestHubModel

pytest.importorskip("dropbot_portable.self_test")

SHORTS_TEST = "test_shorts"


@pytest.fixture
def model():
    return SelfTestHubModel()


def _start(model, tests, board_detected=True):
    model.request_preflight(tests)
    model.apply_preflight(
        SelfTestPreflight(tray_in=True, board_detected=board_detected)
    )

    return model.start_run()


def _result(run_id, name=SHORTS_TEST, verdict=True):
    return SelfTestResult(
        run_id=run_id,
        name=name,
        title=name,
        verdict=verdict,
        duration=1.25,
        result={"shorts": [] if verdict else [3], "duration": 1.25},
    )


def test_run_request_validates_against_the_contract(model):
    request = _start(model, [VOLTAGE_TEST, CHANNELS_TEST])

    validated = SelfTestRunRequest(**request)

    assert validated.run_id == model.run_id
    assert validated.test_kwargs[VOLTAGE_TEST] == {"n": model.parameters.voltage_points}
    assert validated.test_kwargs[CHANNELS_TEST]["threshold_pf"] == pytest.approx(
        model.parameters.channels_threshold_pf
    )
    assert not validated.chip_absent_acknowledged


def test_start_needs_the_tray_in_and_a_board_or_the_go_ahead(model):
    model.request_preflight([SHORTS_TEST])
    preflight = model.preflight

    preflight.apply_reply(SelfTestPreflight(tray_in=False, board_detected=True))
    assert not preflight.can_start

    preflight.apply_reply(SelfTestPreflight(tray_in=True, board_detected=False))
    assert not preflight.can_start

    preflight.chip_absent_acknowledged = True
    assert preflight.can_start
    assert model.start_run()["chip_absent_acknowledged"]


def test_a_run_may_choose_the_tray_out(model):
    model.request_preflight([SHORTS_TEST])
    preflight = model.preflight

    preflight.wants_tray_in = False
    preflight.apply_reply(SelfTestPreflight(tray_in=True, board_detected=True))
    assert not preflight.can_start
    assert "tray OUT" in preflight.start_hint

    preflight.apply_reply(SelfTestPreflight(tray_in=False, board_detected=True))
    assert preflight.can_start

    request = model.start_run()
    assert not request["tray_in"]
    assert not request["run_all"]


def test_run_all_keeps_the_tray_in_and_the_choice(model):
    model.preflight.wants_tray_in = False
    model.request_preflight(model.all_test_names(), run_all=True)
    preflight = model.preflight

    preflight.wants_tray_in = False
    preflight.apply_reply(SelfTestPreflight(tray_in=False, board_detected=True))
    assert preflight.wants_tray_in
    assert not preflight.can_start

    preflight.apply_reply(SelfTestPreflight(tray_in=True, board_detected=True))
    request = SelfTestRunRequest(**model.start_run())
    assert request.tray_in and request.run_all
    assert not preflight.chosen_tray_in


def test_a_run_needs_a_selected_test(model):
    model.request_preflight([])

    assert not model.preflight_pending


def test_start_queues_the_tests_and_leaves_the_preflight(model):
    _start(model, [SHORTS_TEST])

    assert model.running and not model.preflight_pending
    assert model._row(SHORTS_TEST).outcome == OUTCOME_QUEUED


def test_messages_of_another_run_are_ignored(model):
    _start(model, [SHORTS_TEST])

    model.apply_progress(SelfTestProgress(run_id="other", phase="start", total=1))
    model.apply_result(_result("other"))
    model.apply_finished(SelfTestFinished(run_id="other"))

    assert model.running
    assert model.outputs.results == {}
    assert model._row(SHORTS_TEST).outcome == OUTCOME_QUEUED


def test_a_run_goes_through_progress_result_and_finished(model):
    run_id = _start(model, [SHORTS_TEST, VOLTAGE_TEST])["run_id"]

    model.apply_progress(
        SelfTestProgress(run_id=run_id, phase="start", name=SHORTS_TEST, total=2)
    )
    assert model._row(SHORTS_TEST).outcome == OUTCOME_RUNNING
    assert model.run_acknowledged

    model.apply_result(_result(run_id, verdict=False))
    assert model._row(SHORTS_TEST).outcome == OUTCOME_FAIL
    assert model._row(SHORTS_TEST).duration == "1.2 s"
    assert SHORTS_TEST in model.outputs.results and model.outputs.report_markdown

    model.apply_finished(SelfTestFinished(run_id=run_id, unsaved=[UNSAVED_TARE]))
    assert not model.running
    assert model.summary.startswith("Self-test FAILED")
    assert model._row(VOLTAGE_TEST).outcome == OUTCOME_NOT_RUN
    assert model.can_save_calibration and model.can_save_report


def test_progress_text_spans_the_whole_run(model):
    run_id = _start(model, [SHORTS_TEST, VOLTAGE_TEST])["run_id"]

    model.apply_progress(
        SelfTestProgress(
            run_id=run_id,
            phase="step",
            index=1,
            total=2,
            name=VOLTAGE_TEST,
            step=4,
            steps=10,
        )
    )

    assert model.progress == 70
    assert model.step_text == "Test 2 of 2: voltage (step 5 of 10)"


def test_a_refused_run_reports_its_reason(model):
    run_id = _start(model, [SHORTS_TEST])["run_id"]

    model.apply_finished(
        SelfTestFinished(run_id=run_id, refused_reason="a run is already in progress")
    )

    assert not model.running
    assert "a run is already in progress" in model.summary
    assert model._row(SHORTS_TEST).outcome == OUTCOME_NOT_RUN


def test_a_late_result_of_the_ended_run_still_applies(model):
    run_id = _start(model, [SHORTS_TEST])["run_id"]
    model.apply_finished(SelfTestFinished(run_id=run_id, cancelled=True))

    model.apply_result(_result(run_id))

    assert model._row(SHORTS_TEST).outcome == OUTCOME_PASS


def test_reopened_panel_resyncs_to_the_backends_run(model):
    model.apply_preflight(
        SelfTestPreflight(running=True, run_id="theirs", unsaved=[UNSAVED_CALIBRATION])
    )

    assert model.running and model.run_id == "theirs"
    assert model.unsaved == [UNSAVED_CALIBRATION]
    assert not model.can_save_calibration

    model.apply_progress(
        SelfTestProgress(run_id="theirs", phase="choreography", text="HV off")
    )
    assert model.step_text == "HV off"


def test_idle_reply_before_the_run_is_acknowledged_is_not_trusted(model):
    _start(model, [SHORTS_TEST])

    model.apply_preflight(SelfTestPreflight(running=False))

    assert model.running


def test_idle_reply_after_the_run_was_acknowledged_ends_it(model):
    run_id = _start(model, [SHORTS_TEST])["run_id"]
    model.apply_progress(SelfTestProgress(run_id=run_id, phase="start", total=1))

    model.apply_preflight(SelfTestPreflight(running=False))

    assert not model.running


def test_abort_of_an_unacknowledged_run_drops_it(model):
    _start(model, [SHORTS_TEST])

    model.mark_aborting()

    assert not model.running


def test_calibration_save_reply_takes_the_backends_unsaved(model):
    model.unsaved = [UNSAVED_CALIBRATION, UNSAVED_TARE]

    request = model.save_calibration_request()
    assert request == {"calibration": True, "tare": True}
    assert not model.can_save_calibration

    model.apply_calibration_saved(
        SelfTestCalibrationSaved(
            calibration_status=0, tare_ok=False, unsaved=[UNSAVED_TARE]
        )
    )

    assert model.unsaved == [UNSAVED_TARE]
    assert model.can_save_calibration
    assert "NOT saved" in model.calibration_status


def test_a_second_start_neither_requests_nor_replaces_the_run(model):
    run_id = _start(model, [SHORTS_TEST])["run_id"]

    assert model.start_run() is None
    assert model.run_id == run_id and model.running


def test_abandoned_run_is_readopted_when_the_backend_runs_it(model):
    run_id = _start(model, [SHORTS_TEST])["run_id"]

    assert model.mark_aborting() is True
    assert not model.running

    model.apply_preflight(SelfTestPreflight(running=True, run_id=run_id))

    assert model.running and model.run_id == run_id and model.run_acknowledged


def test_acknowledged_abort_waits_for_the_finished_message(model):
    run_id = _start(model, [SHORTS_TEST])["run_id"]
    model.apply_progress(SelfTestProgress(run_id=run_id, phase="start", total=1))

    assert model.mark_aborting() is False
    assert model.running and model.aborting


def test_busy_reply_keeps_the_checklist(model):
    model.request_preflight([SHORTS_TEST])
    model.apply_preflight(SelfTestPreflight(tray_in=True, board_detected=True))

    model.apply_preflight(SelfTestPreflight(error=PREFLIGHT_BOARD_BUSY_ERROR))

    assert model.preflight.can_start and not model.preflight.error


def test_disconnected_reply_pauses_until_a_connected_reply(model):
    model.apply_preflight(SelfTestPreflight(error=PREFLIGHT_DISCONNECTED_ERROR))
    assert not model.preflight.board_connected

    model.apply_preflight(SelfTestPreflight(tray_in=True))
    assert model.preflight.board_connected
