# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test run choreography: planning, the HV-off-before-pad-move
rule, read-back checks, the restore, start refusals and request validation.
Hardware-free, no Redis."""

# Standard library imports.
import threading
from types import SimpleNamespace

# Microdrop package imports.
from portable_dropbot_controller.self_test_choreography import (
    STEP_HV_OFF,
    STEP_PADS,
    STEP_TEST,
    execute_run,
    hv_status_byte,
    plan_restore,
    plan_run,
    preflight_fields,
    start_refusal_reason,
    validate_run_request,
)
from portable_dropbot_controller.self_test_results import unsaved_parts
from portable_dropbot_self_tests.consts import tray_in_required

CALIBRATION = "test_on_board_feedback_calibration"
#: A STATUS reply with a chip on the pads and the test board's chip_res.
BOARD_STATUS = SimpleNamespace(chip_on_pad=7, chip_res=1665)
NO_BOARD_STATUS = SimpleNamespace(chip_on_pad=0, chip_res=75)


class _FakeBoard:
    """The choreography's board: records every call, answers from settings."""

    def __init__(
        self, hv_status=1, pads_follow=True, results=None, lost=False, refusal=""
    ):
        self.log = []
        self.refusal = refusal
        self.hv_status = hv_status
        self.pads_follow = pads_follow
        self.results = results or {}
        self.lost = lost

    def hv_off(self, step):
        self.log.append(("hv_off",))

        return SimpleNamespace(status=self.hv_status)

    def move_pads(self, step):
        self.log.append(("pads", step.target))
        read_back = int(step.target) if self.pads_follow else 0xF2

        return not self.refusal, None if self.refusal else read_back, self.refusal

    def run_test(self, step):
        self.log.append(("test", step.test, step.index))

        return self.results.get(step.test, {"duration": 0.1})

    def between_steps(self):
        pass

    def link_lost(self):
        return self.lost


def _kinds(steps):
    return [(step.kind, step.target, step.test) for step in steps]


# --------------------------------------------------------------------- #
# Planning                                                              #
# --------------------------------------------------------------------- #


def test_plan_run_moves_pads_only_when_the_next_test_needs_them_elsewhere():
    steps = plan_run(
        ["system_info", "test_voltage", CALIBRATION, "test_channels"], False
    )

    assert _kinds(steps) == [
        (STEP_TEST, None, "system_info"),
        (STEP_HV_OFF, None, ""),
        (STEP_PADS, True, ""),
        (STEP_TEST, None, "test_voltage"),
        (STEP_HV_OFF, None, ""),
        (STEP_PADS, False, ""),
        (STEP_TEST, None, CALIBRATION),
        (STEP_HV_OFF, None, ""),
        (STEP_PADS, True, ""),
        (STEP_TEST, None, "test_channels"),
    ]
    assert [step.index for step in steps if step.kind == STEP_TEST] == [0, 1, 2, 3]


def test_plan_run_with_unknown_pads_moves_before_the_first_test_that_cares():
    steps = plan_run(["test_boards", "test_shorts", "test_voltage"], None)

    assert _kinds(steps) == [
        (STEP_TEST, None, "test_boards"),
        (STEP_HV_OFF, None, ""),
        (STEP_PADS, True, ""),
        (STEP_TEST, None, "test_shorts"),
        (STEP_TEST, None, "test_voltage"),
    ]


def test_plan_restore():
    assert _kinds(plan_restore(True, True)) == [(STEP_HV_OFF, None, "")]
    assert _kinds(plan_restore(True, False)) == [
        (STEP_HV_OFF, None, ""),
        (STEP_PADS, True, ""),
    ]
    assert _kinds(plan_restore(False, None)) == [
        (STEP_HV_OFF, None, ""),
        (STEP_PADS, False, ""),
    ]
    assert _kinds(plan_restore(None, True)) == [(STEP_HV_OFF, None, "")]


def test_hv_status_byte():
    assert hv_status_byte(SimpleNamespace(status=1)) == 1
    assert hv_status_byte(2) == 2
    assert hv_status_byte(None) is None
    assert hv_status_byte(True) is None
    assert hv_status_byte(SimpleNamespace(status=False)) is None


# --------------------------------------------------------------------- #
# Execution                                                             #
# --------------------------------------------------------------------- #


def test_run_moves_pads_around_the_calibration_and_restores_them():
    board = _FakeBoard()

    summary = execute_run([CALIBRATION], True, board, threading.Event())

    assert board.log == [
        ("hv_off",),
        ("pads", False),
        ("test", CALIBRATION, 0),
        ("hv_off",),
        ("pads", True),
    ]
    assert summary["error"] == ""
    assert list(summary["results"]) == [CALIBRATION]
    assert summary["restore_note"] == "HV off; pads restored (pressed)"


def test_unconfirmed_hv_off_never_moves_the_pads():
    board = _FakeBoard(hv_status=0)

    summary = execute_run(["test_voltage"], False, board, threading.Event())

    assert ("pads", True) not in board.log
    assert not any(entry[0] in ("pads", "test") for entry in board.log)
    assert "HV off not confirmed" in summary["error"]
    assert summary["restore_note"].startswith("restore incomplete: HV off not")


def test_pad_read_back_mismatch_ends_the_run_and_the_restore_moves_back():
    board = _FakeBoard(pads_follow=False)

    summary = execute_run(
        ["test_voltage", "test_shorts"], False, board, threading.Event()
    )

    assert not any(entry[0] == "test" for entry in board.log)
    assert "read-back mismatch" in summary["error"]
    # Current pad state is unknown after the failed move: the restore tries.
    assert board.log[-2:] == [("hv_off",), ("pads", False)]
    assert "restore incomplete" in summary["restore_note"]


def test_serial_link_error_stops_the_run():
    board = _FakeBoard(results={"system_info": {"error": "SerialException('gone')"}})

    summary = execute_run(
        ["system_info", "test_boards"], None, board, threading.Event()
    )

    assert ("test", "test_boards", 1) not in board.log
    assert "serial link failed" in summary["error"]


def test_ordinary_test_error_does_not_stop_the_run():
    board = _FakeBoard(results={"system_info": {"error": "ValueError('x')"}})

    summary = execute_run(
        ["system_info", "test_boards"], None, board, threading.Event()
    )

    assert ("test", "test_boards", 1) in board.log
    assert summary["error"] == ""


def test_cancel_stops_before_the_next_step_and_still_restores():
    cancel = threading.Event()
    board = _FakeBoard()
    board.run_test = lambda step: (cancel.set(), {"duration": 0.1})[1]

    summary = execute_run(["system_info", "test_voltage"], False, board, cancel)

    assert ("pads", True) not in board.log
    assert list(summary["results"]) == ["system_info"]
    assert board.log == [("hv_off",)]


def test_pad_move_refused_for_unconfirmed_hv_off_leaves_the_pads_alone():
    board = _FakeBoard(refusal="HV off not confirmed (reply 0)")

    summary = execute_run(["test_voltage"], False, board, threading.Event())

    assert not any(entry[0] == "test" for entry in board.log)
    assert "pad press not sent: HV off not confirmed" in summary["error"]
    # The refused move never left the start state: the restore moves nothing.
    assert board.log[-1] == ("hv_off",)
    assert summary["restore_note"] == "HV off; pads already where they started"


def test_a_raising_step_still_restores():
    board = _FakeBoard()

    def explode(step):
        raise RuntimeError("driver blew up")

    board.run_test = explode

    summary = execute_run([CALIBRATION], True, board, threading.Event())

    assert summary["error"] == "driver blew up"
    assert board.log[-2:] == [("hv_off",), ("pads", True)]
    assert summary["hv_off_confirmed"] is True


def test_lost_link_skips_the_whole_restore():
    board = _FakeBoard(lost=True)

    summary = execute_run(["system_info"], True, board, threading.Event())

    assert board.log == [("test", "system_info", 0)]
    assert "restore skipped" in summary["restore_note"]


# --------------------------------------------------------------------- #
# Start refusals and validation                                         #
# --------------------------------------------------------------------- #


def test_unknown_pad_state_refuses_a_run_that_must_move_them():
    reads = {"tray": 0, "pads": None, "status": BOARD_STATUS}

    assert "pad state unknown" in start_refusal_reason(["test_voltage"], reads, False)
    assert start_refusal_reason(["system_info"], reads, False) == ""


def test_the_tray_must_read_where_the_run_wants_it():
    tray_in = {"tray": 0, "pads": 0, "status": BOARD_STATUS}
    tray_out = {"tray": 1, "pads": 0, "status": BOARD_STATUS}
    not_read = {"tray": None, "pads": 0, "status": BOARD_STATUS}

    assert start_refusal_reason(["test_voltage"], tray_in, False) == ""
    assert start_refusal_reason(["test_voltage"], tray_out, False, False) == ""
    assert "tray is not in (out)" in start_refusal_reason(
        ["test_voltage"], tray_out, False
    )
    assert "tray is not out (in)" in start_refusal_reason(
        [CALIBRATION], tray_in, False, False
    )
    assert "no reply" in start_refusal_reason(["system_info"], not_read, False, False)


def test_run_all_and_the_motor_test_need_the_tray_in():
    assert not tray_in_required(["test_voltage", CALIBRATION])
    assert tray_in_required(["test_voltage"], run_all=True)
    assert tray_in_required(["system_info", "test_motors"])


def test_absent_board_needs_the_acknowledgement():
    reads = {"tray": 0, "pads": 0, "status": NO_BOARD_STATUS}

    assert "no board detected" in start_refusal_reason(["system_info"], reads, False)
    assert start_refusal_reason(["system_info"], reads, True) == ""


def test_preflight_fields():
    fields = preflight_fields({"tray": 0, "pads": 1, "status": BOARD_STATUS})

    assert fields == {
        "tray_in": True,
        "pads_pressed": True,
        "chip_on_pad_mask": 7,
        "chip_res": 1665,
        "board_detected": True,
    }
    assert preflight_fields({"tray": None, "pads": 0xF2, "status": None}) == {
        "tray_in": None,
        "pads_pressed": None,
        "chip_on_pad_mask": None,
        "chip_res": None,
        "board_detected": None,
    }


def test_validation_accepts_known_scalar_parameters_and_drops_repeats():
    tests, reason = validate_run_request(
        ["test_voltage", "test_channels", "test_voltage"],
        {"test_voltage": {"n": 3}, "test_channels": {"threshold_pf": 5}},
    )

    assert reason == ""
    assert tests == ["test_voltage", "test_channels"]


def test_validation_refusals():
    cases = [
        (["test_nonsense"], {}, "unknown test"),
        (["test_voltage"], {"test_nonsense": {"n": 1}}, "unknown test"),
        (["test_voltage"], {"test_voltage": {"repeats": 3}}, "not a settable"),
        # Sequence parameters stay out of reach of scalar overrides.
        ([CALIBRATION], {CALIBRATION: {"voltages": 1.0}}, "not a settable"),
        (["test_voltage"], {"test_voltage": {"n": True}}, "is not int"),
        (["test_voltage"], {"test_voltage": {"n": 1}}, "outside 2-20"),
        (["test_voltage"], {"test_voltage": {"n": 2.0}}, "is not int"),
        (["test_channels"], {"test_channels": {"n_reps": 21}}, "outside 1-20"),
        (["test_channels"], {"test_channels": {"threshold_pf": 0.1}}, "outside"),
        ([CALIBRATION], {CALIBRATION: {"max_rail_pct": 60.0}}, "outside"),
        ([CALIBRATION], {CALIBRATION: {"check_other_polarity": True}}, "not a"),
        (["system_info"], {"system_info": {"full": True}}, "not a settable"),
    ]

    for tests, kwargs, expected in cases:
        assert expected in validate_run_request(tests, kwargs)[1]


# --------------------------------------------------------------------- #
# Unsaved calibration state                                             #
# --------------------------------------------------------------------- #


def test_unsaved_parts_follow_what_the_run_captured():
    captured = {
        CALIBRATION: {"cap_calibrate": {"c": 1}, "cap_calibrate_saved": False},
        "test_channels": {"tare_capture": {"ok": True, "saved": False}},
    }

    assert unsaved_parts(captured, []) == ["calibration", "tare"]
    # A run that captured nothing keeps the previous state.
    assert unsaved_parts({"system_info": {}}, ["tare"]) == ["tare"]
    # A capture that saved itself clears its part.
    saved = {CALIBRATION: {"cap_calibrate": {"c": 1}, "cap_calibrate_saved": True}}
    assert unsaved_parts(saved, ["calibration", "tare"]) == ["tare"]
