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
    """Qt-free pre-flight state. A run starts only with the tray in and
    either a detected test board or the operator's explicit go-ahead
    without one."""

    #: The tests the pending run will do, for the intro line.
    tests_text = Str()

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

    #: Start is allowed: tray in, and a test board or the go-ahead.
    can_start = Property(
        Bool, observe="tray_in, board_detected, chip_absent_acknowledged"
    )

    #: What Start is waiting for.
    start_hint = Property(
        Str, observe="tray_in, board_detected, chip_absent_acknowledged, error"
    )

    def reset_for_run(self, titles):
        """Begin a pre-flight check for the tests titled ``titles``."""
        self.chip_absent_acknowledged = False
        self.tests_text = (
            f"Run {len(titles)} test(s): {', '.join(titles)}. The run switches "
            "HV and electrodes and moves the pogo pads itself (never the tray); "
            "afterwards the pads go back to where they are now and the HV is "
            "left off."
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

    def _get_can_start(self):
        return self.tray_in is True and (
            self.board_detected is True or self.chip_absent_acknowledged
        )

    def _get_start_hint(self):
        if self.error:
            return f"Board state not read: {self.error}"

        if self.tray_in is not True:
            return "Start needs the tray IN (use Tray in, then Refresh)."

        if self.board_detected is not True and not self.chip_absent_acknowledged:
            return (
                "No test board detected: press the pads to read the board ID, "
                "or tick the box to run anyway."
            )

        return "Ready."
