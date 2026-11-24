# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Portable DropBot device constants: serial link, HV, lighting,
capacitance calibration, connection monitoring and fans."""

#: Serial defaults for the Portable Dropbot boards. The driver's
#: connect() probes its own baud whitelist beyond this starting rate.
DEFAULT_BAUD_RATE = 115200

#: Channel-count fallback for request validation before the driver's
#: own board detection (120 or 200) has answered.
DEFAULT_NUM_CHANNELS = 200

#: HV actuation defaults (both Int end-to-end, like every device) and
#: UI setpoint bounds, carried over from the original portable pane
#: (which drove this same hardware).
DEFAULT_VOLTAGE = 100
DEFAULT_FREQUENCY = 10_000
VOLTAGE_BOUNDS = (30, 200)
FREQUENCY_BOUNDS = (50, 60_000)

#: Illumination LED brightness (%), applied on connect and from the
#: status pane's spinner. The firmware takes a raw 0-255 byte.
LIGHT_INTENSITY_BOUNDS = (0, 100)
DEFAULT_LIGHT_INTENSITY = 50
LIGHT_INTENSITY_RAW_MAX = 255

#: RGB indicator LED states the signal board knows.
RGB_LIGHT_STATES = ("off", "red", "green", "yellow")

#: ML calibration runs at EXACTLY this V/F (hardware-validated by the
#: vendor's own calibration macro; anything else invalidates the fit).
CAL_VOLTAGE = 100
CAL_FREQUENCY = 10_000

#: Electrode-path capacitance gain (permille, EF-persisted); 692 is
#: the vendor's HW-benchmark default for the 10 pF/channel board.
ELECTRODE_GAIN_PERMILLE_BOUNDS = (0, 5000)
DEFAULT_ELECTRODE_GAIN_PERMILLE = 692

#: Multi-slope reference-cap provisioning: 3 = 10/100/470 pF board,
#: 5 = new board adding 1000/2200 pF.
CAL_CAPS_CHOICES = (3, 5)

#: Seconds between monitor ticks: a port scan while disconnected, a
#: status poll (published to the panes) while connected.
MONITOR_INTERVAL_S = 2

#: Budget for one driver connect before it is abandoned (#1065). A board
#: answers both logins in well under a second; a port that is not the
#: board can swallow the login write forever, since the driver opens the
#: port without a write timeout. Single-rate: open + two 2 s logins.
CONNECT_TIMEOUT_S = 10
#: Autodetect walks four baud rates at up to ~5 s each, then the motor login.
CONNECT_AUTODETECT_TIMEOUT_S = 30
#: Write timeout forced onto an abandoned attempt's port so the driver's
#: next login write fails fast instead of blocking again.
ABANDONED_CONNECT_WRITE_TIMEOUT_S = 0.5
#: How long an abandoned attempt's release keeps unblocking its writes
#: before closing the session regardless.
ABANDONED_CONNECT_RELEASE_S = 15
#: How often that release re-cancels a stuck write (the autodetect ladder
#: reopens the port at each baud rate).
ABANDONED_CONNECT_POLL_S = 0.5

#: Consecutive status polls with neither board answering before the
#: link is declared dead and scanning resumes. Without this a silent
#: board is polled forever — every poll a stack of command timeouts
#: that overruns the tick and floods the log — while the UI says
#: "Active".
STATUS_FAILURE_DISCONNECT_LIMIT = 3

#: MCU firmware that pushes change-only status events (EVT_FIELDS,
#: dropbot-portable 1.8.0). From here the panes follow the events and the
#: STATUS poll only resyncs; older firmware accepts the event bit and sends
#: nothing, so it stays on the poll.
STATUS_EVENTS_MIN_MCU_FIRMWARE = (1, 0, 1, 33)

#: The board's event-stream interval (SET_REPORT_CYCLE2, ms): how often a
#: status pass checks the fields between electrode updates. The vendor's
#: ``enable_events`` default.
STATUS_EVENTS_REPORT_INTERVAL_MS = 1000

#: At most one event-merged status publish per this many seconds; the
#: latest merged sample always goes out once the interval has passed.
STATUS_EVENTS_PUBLISH_INTERVAL_S = 0.5

#: While events flow, a full STATUS read (resync and link check) at least
#: this often. A seq gap or a missing base asks for one at the next tick.
STATUS_EVENTS_RESYNC_INTERVAL_S = 30

#: No event frame for this long means the stream has stopped: the firmware
#: resends every subscribed field every 5 s. The monitor goes back to the
#: full poll and re-sends the subscription once per resync interval.
STATUS_EVENTS_STALE_S = 12

#: Once a firmware update (the vendor flash tool) releases its priority lease
#: on our port, wait this long before scanning again — the vendor UI's
#: YIELD_RECONNECT_DELAY_S.
PORT_LEASE_RELEASE_DELAY_S = 2.0

#: How long each de-energize command (HV off, electrodes cleared, PMT off)
#: waits for its answer when the link is closed on purpose, so a dead board
#: cannot stall the disconnect — the vendor UI's SHUTDOWN_TIMEOUT_S.
SHUTDOWN_TIMEOUT_S = 1.0

#: Pause before the one retry of a firmware version read that went
#: unanswered at connect: a board still busy with its boot homing answers
#: late.
FIRMWARE_READ_RETRY_DELAY_S = 1.0

#: Boards whose fans the driver's setFan(on, board=...) drives, by the
#: driver's own names: the MCU (signal) board fan or the motor board fans.
FAN_BOARDS = ("signal", "motor")
#: The board the status pane's fan toggle drives unless the Portable
#: DropBot Settings preference says otherwise.
DEFAULT_FAN_BOARD = "signal"
