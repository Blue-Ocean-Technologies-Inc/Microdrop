# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test hub's run choreography, free of Traits, Qt and messaging.

Ported from the driver bench UI's ``dropbot_portable.ui.self_test_runner``
(not imported: that module needs PySide6). Each selected test runs as its
own ``self_test(tests=[name])`` call; between tests the pogo pads move to
where the next test wants them (``TEST_PADS``: pressed, up, or either):

* the pad state before the run is read first; it is what the pads go back
  to at the end, on abort and on error;
* the HV is switched off, and the off CONFIRMED (status 1), before every
  pad move; a move is never sent when the off is not confirmed;
* every pad move is read back, and a move whose read-back does not match the
  target ends the run;
* the restore switches the HV off, then moves the pads back to their initial
  state; it is skipped entirely when the link to the board is lost.

``execute_run`` drives the sequence through a ``board`` object (the backend
mixin's per-run adapter, or a test fake) with these methods:

* ``hv_off(step)`` -> the raw HV_ENABLE(0) reply;
* ``move_pads(step)`` -> ``(accepted, read-back PUSHPAD_READ byte,
  refusal)``: refusal is why the move was not sent ("" when it was);
* ``run_test(step)`` -> the test's vendor result dict, or None when it was
  cancelled before it started;
* ``between_steps()`` -> called after every step (status refresh);
* ``link_lost()`` -> True once the board has disconnected.
"""

# Standard library imports.
from collections import namedtuple

# Third-party imports.
from dropbot_portable import self_test as vendor_self_test

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: PUSHPAD_READ / STATUS bytes the choreography decodes.
PADS_PRESSED_BYTE = 1
PADS_RELEASED_BYTE = 0
HV_OFF_CONFIRMED = 1
CHIP_ON_PAD_PRESENT_BIT = 0x1
TRAY_IN_BYTE = 0
TRAY_OUT_BYTE = 1
#: STATUS chip_res window of the capacitor test board (raw counts), read
#: with the pads pressed; the vendor pre-flight's TEST_BOARD_CHIP_RES_RANGE.
TEST_BOARD_CHIP_RES_RANGE = (1200, 2200)
CALIBRATION_TEST = "test_on_board_feedback_calibration"

#: What a run request's test_kwargs may set: test -> parameter -> (type,
#: low, high). Same bounds as the hub's parameter editor
#: (portable_dropbot_self_tests/models/consts.py, the vendor tab's spin
#: boxes); anything else is refused.
TEST_KWARG_BOUNDS = {
    "test_voltage": {"n": (int, 2, 20)},
    CALIBRATION_TEST: {
        "n_reps": (int, 1, 50),
        "min_counts": (float, 1.0, 2000.0),
        "max_rail_pct": (float, 0.0, 50.0),
    },
    "test_channels": {
        "n_reps": (int, 1, 20),
        "threshold_pf": (float, 0.5, 100.0),
    },
}

#: Exception class names a vendor per-test error repr starts with when the
#: serial link itself failed; the run stops instead of trying the next test.
LINK_ERROR_NAMES = (
    "OSError",
    "IOError",
    "SerialException",
    "SerialTimeoutException",
    "PortNotOpenError",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "BrokenPipeError",
    "FileNotFoundError",
    "PermissionError",
)

STEP_HV_OFF = "hv_off"
STEP_PADS = "pads"
STEP_TEST = "test"

#: One choreography step. ``index`` is the run position of the test the step
#: belongs to (or precedes); ``target`` is True for pressed, False for up.
Step = namedtuple("Step", "kind index target test text", defaults=(None, "", ""))


# --------------------------------------------------------------------- #
# Planning                                                              #
# --------------------------------------------------------------------- #


def pad_target(test):
    """Where ``test`` wants the pads: True pressed, False up, None either."""
    need = vendor_self_test.TEST_PADS.get(test, vendor_self_test.PADS_ANY)

    return {vendor_self_test.PADS_DOWN: True, vendor_self_test.PADS_UP: False}.get(need)


def pad_text(target, test=""):
    if target:
        return "Pressing pads..."

    return (
        "Lifting pads for calibration..."
        if test == CALIBRATION_TEST
        else "Lifting pads..."
    )


def needs_pad_move(tests, initial):
    """Whether running ``tests`` from pad state ``initial`` moves the pads."""
    return any(step.kind == STEP_PADS for step in plan_run(tests, initial))


def plan_run(tests, initial):
    """The run's steps: per test, an HV-off and a pad move when the test wants
    the pads elsewhere than they are, then the test. ``initial`` None
    (unknown) plans a move before the first test that cares."""
    steps = []
    current = initial

    for index, name in enumerate(tests):
        target = pad_target(name)

        if target is not None and current is not target:
            steps.append(Step(STEP_HV_OFF, index, text="HV off before the pad move..."))
            steps.append(Step(STEP_PADS, index, target, text=pad_text(target, name)))
            current = target

        steps.append(Step(STEP_TEST, index, test=name))

    return steps


def plan_restore(initial, current, index=0):
    """HV off, then the pads back to ``initial`` when they may be elsewhere
    (``current`` unknown counts as elsewhere). Unknown ``initial``: no move."""
    steps = [Step(STEP_HV_OFF, index, text="Switching HV off...")]

    if initial is not None and current is not initial:
        where = "pressed" if initial else "up"
        steps.append(
            Step(STEP_PADS, index, initial, text=f"Restoring pads ({where})...")
        )

    return steps


# --------------------------------------------------------------------- #
# Decoding                                                              #
# --------------------------------------------------------------------- #


def hv_status_byte(value):
    """Status byte of an HV_ENABLE reply: the generated proxy returns a
    response with ``status``, older paths a plain int; None, a bool or
    anything without a status is "not confirmed"."""

    if value is None or isinstance(value, bool):
        return None

    status = getattr(value, "status", value)

    if isinstance(status, bool):
        return None

    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def pads_state(pads_byte):
    """PUSHPAD_READ byte -> True pressed, False up, None unknown."""
    return {PADS_PRESSED_BYTE: True, PADS_RELEASED_BYTE: False}.get(pads_byte)


def pads_text(pads_byte):
    if pads_byte is None:
        return "no reply"

    return {PADS_PRESSED_BYTE: "pressed", PADS_RELEASED_BYTE: "up"}.get(
        pads_byte, f"state 0x{int(pads_byte):02X}"
    )


def tray_text(tray_byte):
    if tray_byte is None:
        return "no reply"

    return {TRAY_IN_BYTE: "in", TRAY_OUT_BYTE: "out"}.get(
        tray_byte, f"state 0x{int(tray_byte):02X}"
    )


def is_link_error(error):
    """Whether a vendor per-test error repr names a serial-link failure."""
    return str(error or "").split("(", 1)[0].strip() in LINK_ERROR_NAMES


def is_test_board(chip_res):
    """chip_res inside the test-board window; None when it was not read."""

    if chip_res is None:
        return None

    low, high = TEST_BOARD_CHIP_RES_RANGE

    return low <= int(chip_res) <= high


# --------------------------------------------------------------------- #
# Board reads (the caller holds the proxy lock)                         #
# --------------------------------------------------------------------- #


def read_board_state(bot):
    """The tray and pad bytes and the signal-board STATUS, one read each."""
    return {
        "tray": bot.uart.getTray(),
        "pads": bot.uart.getPogo(),
        "status": bot.sig.status(),
    }


def preflight_fields(reads):
    """The SelfTestPreflight board fields of a ``read_board_state`` result."""
    status = reads.get("status")
    tray = reads.get("tray")
    chip_on_pad = None if status is None else int(status.chip_on_pad)
    chip_res = None if status is None else int(status.chip_res)

    return {
        "tray_in": None if tray is None else tray == TRAY_IN_BYTE,
        "pads_pressed": pads_state(reads.get("pads")),
        "chip_on_pad_mask": chip_on_pad,
        "chip_res": chip_res,
        "board_detected": is_test_board(chip_res),
    }


def board_present(reads):
    """A chip on the pads (chip_on_pad bit0) or the test board's chip_res."""
    fields = preflight_fields(reads)
    contact = fields["chip_on_pad_mask"]

    return bool(contact is not None and contact & CHIP_ON_PAD_PRESENT_BIT) or bool(
        fields["board_detected"]
    )


# --------------------------------------------------------------------- #
# Validation (before any HV change or pad move)                         #
# --------------------------------------------------------------------- #


def value_fits(value, kind):
    """An int parameter takes ints only, a float one ints or floats; bools
    never pass (they are ints to Python)."""

    if isinstance(value, bool):
        return False

    if kind is int:
        return isinstance(value, int)

    return isinstance(value, (int, float))


def validate_run_request(tests, test_kwargs):
    """Check a run request against the vendor catalogue.

    Returns
    -------
    tuple
        ``(tests, reason)``: the tests in request order with repeats dropped,
        and why the request is refused ("" when it is valid).
    """
    unknown = [name for name in tests if name not in vendor_self_test.ALL_TESTS]

    if unknown:
        return [], f"unknown test(s): {', '.join(unknown)}"

    for name, overrides in test_kwargs.items():
        if name not in vendor_self_test.ALL_TESTS:
            return [], f"test_kwargs for unknown test {name!r}"

        allowed = TEST_KWARG_BOUNDS.get(name, {})

        for key, value in overrides.items():
            if key not in allowed:
                return [], f"{name}: {key!r} is not a settable parameter"

            kind, low, high = allowed[key]

            if not value_fits(value, kind):
                return [], f"{name}: {key}={value!r} is not {kind.__name__}"

            if not low <= value <= high:
                return [], f"{name}: {key}={value!r} is outside {low}-{high}"

    return list(dict.fromkeys(tests)), ""


def start_refusal_reason(tests, reads, chip_absent_acknowledged, tray_in=True):
    """Why the run start read refuses the run; "" lets it start. ``tray_in``
    is where the run wants the tray (True in, False out), as the vendor
    pre-flight's Start requires the tray at the chosen position."""
    pads_byte = reads.get("pads")
    tray_byte = reads.get("tray")

    initial = pads_state(pads_byte)

    if initial is None and needs_pad_move(tests, None):
        return (
            f"pad state unknown ({pads_text(pads_byte)}); the run needs to move "
            f"the pads, so nothing was started"
        )

    if tray_byte != (TRAY_IN_BYTE if tray_in else TRAY_OUT_BYTE):
        return (
            f"the tray is not {'in' if tray_in else 'out'} "
            f"({tray_text(tray_byte)}), where the run wants it"
        )

    if not chip_absent_acknowledged and not board_present(reads):
        return (
            "no board detected on the pads (chip_on_pad clear, chip_res outside "
            "the test-board window) and the operator did not acknowledge it"
        )

    return ""


# --------------------------------------------------------------------- #
# Execution                                                             #
# --------------------------------------------------------------------- #


def _move_pads(board, step, current):
    """Send one pad move and check its read-back; returns
    ``(pad state afterwards, error)`` with error "" on success."""
    accepted, read_back, refusal = board.move_pads(step)
    word = "press" if step.target else "release"

    # A refused move was never sent: the pads are still where they were.
    if refusal:
        return current, f"pad {word} not sent: {refusal}"

    if accepted and pads_state(read_back) is step.target:
        return step.target, ""

    why = "read-back mismatch" if accepted else "not accepted"

    return None, f"pad {word} failed ({why}; pads report {pads_text(read_back)})"


def _hv_off(board, step):
    """Switch the HV off; returns "" when confirmed, else why not."""
    status = hv_status_byte(board.hv_off(step))

    if status == HV_OFF_CONFIRMED:
        return ""

    return f"HV off not confirmed (reply {status!r}); pads not moved"


def execute_run(tests, initial, board, cancel):
    """Run ``tests`` from pad state ``initial``, then always restore.

    Returns
    -------
    dict
        ``results`` (name -> vendor result), ``error`` (what ended the run
        early), ``restore_note`` (what the restore did, or why not) and
        ``hv_off_confirmed`` (the restore's HV off was confirmed).
    """
    results = {}
    error = ""
    current = initial

    try:
        for step in plan_run(tests, initial):
            if cancel.is_set() or error:
                break

            if step.kind == STEP_HV_OFF:
                error = _hv_off(board, step)

            elif step.kind == STEP_PADS:
                current, error = _move_pads(board, step, current)

            else:
                result = board.run_test(step)

                # None: the cancel landed before the test started.
                if result is None:
                    break

                results[step.test] = result

                if is_link_error(result.get("error")):
                    error = f"{step.test}: serial link failed ({result['error']})"

                elif result.get("cancelled"):
                    break

            board.between_steps()
    except Exception as exc:
        # Broad except: whatever broke mid-run, the restore below must still
        # switch the HV off and bring the pads back.
        logger.error(f"Self-test run step FAILED: {exc}", exc_info=True)
        error = str(exc) or repr(exc)

    try:
        restore_note, hv_off_confirmed = restore(initial, current, board, len(tests))
    except Exception as exc:
        logger.error(f"Self-test restore FAILED: {exc}", exc_info=True)
        restore_note, hv_off_confirmed = f"restore failed: {exc!r}", False

    return {
        "results": results,
        "error": error,
        "restore_note": restore_note,
        "hv_off_confirmed": hv_off_confirmed,
    }


def restore(initial, current, board, index=0):
    """HV off, then the pads back to ``initial``; returns ``(restore note,
    HV off confirmed)``. Nothing is sent once the link is lost, and no pad
    moves without a confirmed HV off."""

    if board.link_lost():
        return "the board disconnected: HV off and pad restore skipped", False

    notes = []
    hv_off_confirmed = False

    for step in plan_restore(initial, current, index):
        if step.kind == STEP_HV_OFF:
            why = _hv_off(board, step)

            if why:
                notes.append(f"restore incomplete: {why}")
                break

            hv_off_confirmed = True
            notes.append("HV off")

        else:
            current, why = _move_pads(board, step, current)
            where = "pressed" if step.target else "up"
            notes.append(
                f"restore incomplete: {why}" if why else f"pads restored ({where})"
            )

    if initial is None:
        notes.append("pad state unknown at start, pads not moved")

    elif current is initial and len(notes) == 1:
        notes.append("pads already where they started")

    return "; ".join(notes), hv_off_confirmed
