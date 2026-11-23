# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""De-energize the instrument before a deliberate close of its port, as the
vendor UI's Disconnect, firmware-update yield and window close do
(``SerialWorker.shutdown_deenergize``): HV off and PMT power off, each answer
awaited at most SHUTDOWN_TIMEOUT_S so a dead board cannot stall the close.
The electrodes are cleared as well, after the HV off (``DropBotUart.halt``'s
order), so no pattern from this session is still latched when HV next
comes on. A link that is already gone is closed without these commands,
like the vendor's lost-link path. Heaters a host workflow is driving (the
self-test heat step) are switched off the same way (``switch_heaters_off``,
the vendor worker's ``shutdown_heaters``)."""

# Third-party imports.
from dropbot_portable import SignalBoardProxy

# Local imports.
from .consts import SHUTDOWN_TIMEOUT_S


class BoundedTransport:
    """DropBotUart facade for the shutdown commands: every request waits at
    most ``timeout_s`` for its reply and for the per-command guard, so the
    generated proxy keeps its wire format without queueing for its full
    protocol timeout behind a long motion (the vendor's
    ``_BoundedTransport``)."""

    def __init__(self, uart, timeout_s):
        self._uart = uart
        self._timeout_s = timeout_s

    def _make_cmd_packet(self, cmd, payload):
        return self._uart._make_cmd_packet(cmd, payload)

    def _w(self, data):
        return self._uart._w(data)

    def _wr(self, wbuf, cmd, timeout_s=1.0, min_len=0):
        return self._uart._wr(
            wbuf,
            cmd,
            timeout_s=min(timeout_s, self._timeout_s),
            min_len=min_len,
            lock_timeout_s=min(0.2, self._timeout_s),
        )


def deenergize_session(session, timeout_s=SHUTDOWN_TIMEOUT_S):
    """Switch HV off, clear every electrode and power the PMT off, best
    effort, on a session about to close. Return one outcome line per
    command for the log; never raises."""
    sig = _bounded_signal_proxy(session, timeout_s)

    if sig is None:
        return []

    no_channels = bytes((int(session.uart.board_channels) + 7) // 8)

    return _send_bounded(
        (
            ("hv_enable(0, 0)", lambda: sig.hv_enable(0, 0)),
            ("clear channels", lambda: sig.electrode_state_ch(no_channels)),
            ("pmt_power(0)", lambda: sig.pmt_power(0)),
        )
    )


def switch_heaters_off(session, channels, timeout_s=SHUTDOWN_TIMEOUT_S):
    """TEMP_START_STOP 0 on each heater loop of ``channels``, bounded and best
    effort like ``deenergize_session``. Return one outcome line per channel
    for the log; never raises."""
    sig = _bounded_signal_proxy(session, timeout_s)

    if sig is None:
        return []

    return _send_bounded(
        (
            (
                f"temp_start_stop({channel}, 0)",
                lambda channel=channel: sig.temp_start_stop(channel=channel, enable=0),
            )
            for channel in channels
        )
    )


def _bounded_signal_proxy(session, timeout_s):
    """A signal-board proxy over ``BoundedTransport``; None when the signal
    board is not attached."""
    uart = getattr(session, "uart", None)

    if uart is None or not getattr(uart, "sig_board_connected", False):
        return None

    return SignalBoardProxy(BoundedTransport(uart, timeout_s))


def _send_bounded(commands):
    """Send each ``(label, command)`` in turn, whatever the others do; return
    one outcome line per command."""
    steps = []

    for label, command in commands:
        try:
            reply = command()
        except Exception as error:
            # Broad by design: the port must close whatever a command does.
            steps.append(f"{label} -> FAILED: {error}")
            continue

        answered = reply is not None and reply is not False
        steps.append(f"{label} -> {'OK' if answered else 'NO REPLY'}")

    return steps
