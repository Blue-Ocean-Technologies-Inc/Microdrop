# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pre-run checklist: the board state of the latest preflight reply,
and whether the run may start."""

# Enthought library imports.
from traits.api import Bool, Button, Event, HasTraits, Int, Property, Str, Union

# Local imports.
from ..consts import PREFLIGHT_BOARD_BUSY_ERROR
from .consts import PREFLIGHT_DISCONNECTED_ERROR

#: STATUS chip_on_pad bit0: debounced pad contact, the bit the HV interlock
#: uses (bits 1-2 are raw per-side diagnostics).
CHIP_ON_PAD_CONTACT_BIT = 0x1


class PreflightModel(HasTraits):
    """Qt-free pre-flight state. A run starts only with the tray where the
    run wants it and either a detected test board or the operator's
    explicit go-ahead without one."""

    #: The tests the pending run will do, for the intro line.
    tests_text = Str()

    #: The pending run needs the tray IN (Run all, or a tray-in test).
    tray_required = Bool(False)

    #: The operator's tray position for runs that allow either (True =
    #: in); kept across runs, as the vendor keeps it for the session.
    chosen_tray_in = Bool(True)

    #: Where the pending run wants the tray: IN when required, else the
    #: operator's choice (which the setter records).
    wants_tray_in = Property(Bool, observe="tray_required, chosen_tray_in")

    #: The tray reads where the pending run wants it.
    tray_ok = Property(Bool, observe="tray_in, wants_tray_in")

    # The latest SelfTestPreflight reply; None = could not be read.
    tray_in = Union(None, Bool)
    pads_pressed = Union(None, Bool)
    chip_on_pad_mask = Union(None, Int)
    chip_res = Union(None, Int)
    board_detected = Union(None, Bool)

    #: The reply's refusal or read failure.
    error = Str()

    #: False once a reply said the board is disconnected; polling pauses
    #: until a reply (Refresh, or reopening the panel) says otherwise.
    board_connected = Bool(True)

    #: Fires on every reply, busy ones included, so a poll can follow it.
    replied = Event()

    #: The operator confirmed starting without a detected test board.
    chip_absent_acknowledged = Bool(False)

    refresh_button = Button("Refresh")
    tray_in_button = Button("Tray in")
    tray_out_button = Button("Tray out")
    pads_press_button = Button("Pogos engage")
    pads_release_button = Button("Pogos release")
    start_button = Button("Start")
    cancel_button = Button("Cancel")

    tray_text = Property(Str, observe="tray_in")
    pads_text = Property(Str, observe="pads_pressed")
    chip_text = Property(Str, observe="chip_on_pad_mask")
    board_text = Property(Str, observe="board_detected, chip_res")

    #: Start is allowed: the tray where wanted, and a test board or the
    #: go-ahead.
    can_start = Property(
        Bool, observe="tray_ok, board_detected, chip_absent_acknowledged"
    )

    #: What Start is waiting for.
    start_hint = Property(
        Str,
        observe="tray_ok, wants_tray_in, board_detected, chip_absent_acknowledged, "
        "error",
    )

    def reset_for_run(self, titles, tray_required):
        """Begin a pre-flight check for the tests titled ``titles``;
        ``tray_required`` locks the run to the tray IN."""
        self.chip_absent_acknowledged = False
        self.tray_required = tray_required
        self.tests_text = (
            f"Run {len(titles)} test(s): {', '.join(titles)}. Preparation: the "
            "tray goes to the chosen position and the pogo pads press (by hand, "
            "with the buttons below). Run: the tests switch HV and electrodes "
            "and only the pads move. Cleanup: the pads go back to where they "
            "were and the HV is left off."
        )

    def apply_reply(self, reply):
        """Take the board state of a SelfTestPreflight reply. A busy board
        is a passing state, not news: its reply keeps the last checklist."""
        self.replied = True

        if reply.error.startswith(PREFLIGHT_BOARD_BUSY_ERROR):
            return

        self.board_connected = not reply.error.startswith(PREFLIGHT_DISCONNECTED_ERROR)
        self.tray_in = reply.tray_in
        self.pads_pressed = reply.pads_pressed
        self.chip_on_pad_mask = reply.chip_on_pad_mask
        self.chip_res = reply.chip_res
        self.board_detected = reply.board_detected
        self.error = reply.error

    def _get_tray_text(self):
        return {None: "not read", True: "in", False: "OUT"}[self.tray_in]

    def _get_pads_text(self):
        return {None: "not read", True: "pressed", False: "up"}[self.pads_pressed]

    def _get_chip_text(self):
        if self.chip_on_pad_mask is None:
            return "not read"

        if self.chip_on_pad_mask & CHIP_ON_PAD_CONTACT_BIT:
            return "chip detected"

        return "NO chip detected (pads up, or no contact)"

    def _get_board_text(self):
        if self.board_detected is None:
            return "not read"

        reading = "" if self.chip_res is None else f" (chip_res {self.chip_res})"

        if self.board_detected:
            return f"test board detected{reading}"

        return (
            f"no / unknown board{reading}; the test board is recognised only "
            "with the pads pressed"
        )

    def _get_wants_tray_in(self):
        return self.tray_required or self.chosen_tray_in

    def _set_wants_tray_in(self, value):
        if not self.tray_required:
            self.chosen_tray_in = value

    def _get_tray_ok(self):
        return self.tray_in is not None and self.tray_in == self.wants_tray_in

    def _get_can_start(self):
        return self.tray_ok and (
            self.board_detected is True or self.chip_absent_acknowledged
        )

    def _get_start_hint(self):
        if self.error:
            return f"Board state not read: {self.error}"

        if not self.tray_ok and self.wants_tray_in:
            return "Start needs the tray IN (use Tray in, then Refresh)."

        if not self.tray_ok:
            return (
                "Start needs the tray OUT (use Tray out, then Refresh), or "
                "choose In above."
            )

        if self.board_detected is not True and not self.chip_absent_acknowledged:
            return (
                "No test board detected: press the pads to read the board ID, "
                "or tick the box to run anyway."
            )

        return "Ready."
