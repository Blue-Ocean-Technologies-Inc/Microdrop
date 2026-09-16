# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure helpers for the portable PMT sessions: the multi-spot capture, the
PMT Capture pane's live stream, and the buffered acquire. All three claim
the same hardware in turn (see the mixin service's shared claim) but each
has its own sample-collection shape here:

- ``StreamAssembler`` — a capture spot's whole exposure, kept in strict
  packet order with duplicate/wrap handling, for ``calibrate_period`` and
  the CSV.
- ``LiveStreamBuffer`` — the live stream's samples between one publish
  tick and the next; no ordering or duplicate bookkeeping needed, a
  dropped frame just skips part of one UI update.
- the buffered acquire has no assembler here — its packets come back
  through the driver's own collector (``uart.pmt_acquire_collect``), which
  returns a complete ``PmtCapture`` in one call.

Ported from the driver bench UI (``dropbot_portable.ui.tabs.pmt_tab``),
whose stats and CSV writer are module-level but live in a Qt module and
whose stream assembly is inline in a Qt method. Kept here so the CSVs
Microdrop writes stay interchangeable with the bench's without the backend
importing Qt. No Qt, no driver import: all unit-testable without hardware.

Stream frame layout (``CMD_PMT_STREAM_DATA`` 0x123F, all little-endian)::

    [pkt_idx u16][n u16][n x u16 samples]

``pkt_idx`` restarts at 0 on every stream start and wraps at 65535; the
firmware ships every frame exactly once (no retransmission), so a repeated
absolute index is an aliased frame, not data.
"""

# Standard library imports.
import math
import struct
import threading
import time
from datetime import datetime

# Local imports.
from .consts import PMT_PARK_LOCATION, PMT_SPOT_SLOTS

#: Absolute-index step that reads as a u16 counter wrap rather than a
#: duplicated/aliased frame.
_WRAP_THRESHOLD = 0x8000
_HEADER = struct.Struct("<HH")
#: Park location followed by one int32 per spot (PMTPositionParams.pos).
_POSITIONS = struct.Struct(f">{PMT_PARK_LOCATION + PMT_SPOT_SLOTS}i")
#: Firmware from before the park extension serves five locations.
_LEGACY_POSITIONS_BYTES = 5 * 4


def decode_stream_frame(data):
    """Decode one ``CMD_PMT_STREAM_DATA`` frame; return ``(idx, values)``,
    or ``None`` when the frame is too short or its declared count doesn't
    fit the payload — a torn or truncated frame, never valid data."""

    if len(data) < _HEADER.size:
        return None

    idx, n = _HEADER.unpack_from(data)

    if not n or len(data) < _HEADER.size + 2 * n:
        return None

    return idx, struct.unpack_from(f"<{n}H", data, _HEADER.size)


class StreamAssembler:
    """Assemble one stream session's frames into an ordered sample list.

    ``feed`` is the transport subscriber callback and runs on the RX
    thread; everything else is read on the routine's thread, so state is
    guarded by a lock and read out through ``snapshot``.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._samples = []
        self._sample_index = []
        self._arrivals = []
        self._seen = set()
        self._last_idx = -1
        self._epoch = 0
        self._first_abs = -1
        self.packets = 0
        self.duplicates = 0
        self.samples_per_packet = 0

    def feed(self, cmd, data, now=None):
        """Record one frame; return True when it added samples."""
        decoded = decode_stream_frame(data)

        if decoded is None:
            return False

        idx, values = decoded
        n = len(values)
        arrival = time.monotonic() if now is None else now

        with self._lock:
            prev = self._last_idx
            if prev >= 0 and prev - idx > _WRAP_THRESHOLD:
                self._epoch += 1
                self._last_idx = idx
            elif idx > prev:
                self._last_idx = idx
            abs_idx = self._epoch * 0x10000 + idx
            if abs_idx in self._seen:
                self.duplicates += 1
                return False
            self._seen.add(abs_idx)
            if self._first_abs < 0:
                self._first_abs = abs_idx
                self.samples_per_packet = n
            base = (abs_idx - self._first_abs) * n
            self.packets += 1
            self._samples.extend(values)
            self._sample_index.extend(base + i for i in range(n))
            self._arrivals.append((abs_idx, arrival))
        return True

    def snapshot(self):
        """Return copies of (samples, per-sample absolute index, arrivals)."""
        with self._lock:
            return list(self._samples), list(self._sample_index), list(self._arrivals)


class LiveStreamBuffer:
    """Accumulate one live-stream session's frames between publish ticks.

    ``feed`` is the transport subscriber callback and runs on the RX
    thread; ``drain`` runs on the publish loop's thread, so state is
    guarded by a lock. Unlike ``StreamAssembler`` there is no duplicate or
    wrap tracking: a dropped or aliased live frame only skips part of one
    UI update, which isn't worth the bookkeeping a recorded capture needs.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._samples = []
        self._packets = 0

    def feed(self, cmd, data):
        """Record one frame; return True when it added samples."""
        decoded = decode_stream_frame(data)

        if decoded is None:
            return False

        _idx, values = decoded

        with self._lock:
            self._samples.extend(values)
            self._packets += 1

        return True

    def drain(self):
        """Return (samples, packets) collected since the last drain, and
        reset both counters."""
        with self._lock:
            samples, packets = self._samples, self._packets
            self._samples = []
            self._packets = 0

        return samples, packets


def calibrate_period(assembler, avg):
    """Return (seconds per sample, "measured" | "estimated").

    The nominal ``avg / 1000`` estimate is known to be wrong by ~40 % at
    avg=16 / osr=6, so the period is measured from the packet cadence when
    at least two packets arrived and the measurement is within [0.25x, 10x]
    of the estimate (a burst arrival measures near zero and is rejected).
    """
    estimate = (avg or 1) / 1000.0
    _, _, arrivals = assembler.snapshot()
    per_packet = assembler.samples_per_packet
    if len(arrivals) >= 2 and arrivals[-1][0] > arrivals[0][0] and per_packet:
        span_s = arrivals[-1][1] - arrivals[0][1]
        measured = span_s / ((arrivals[-1][0] - arrivals[0][0]) * per_packet)
        if estimate * 0.25 <= measured <= estimate * 10:
            return measured, "measured"
    return estimate, "estimated"


def capture_stats(samples):
    """Return (n, mean, sample sd, min, max) of raw ADC counts."""
    n = len(samples)
    if n == 0:
        return 0, 0.0, 0.0, 0, 0
    mean = sum(samples) / n
    sd = math.sqrt(sum((s - mean) ** 2 for s in samples) / (n - 1)) if n > 1 else 0.0
    return n, mean, sd, min(samples), max(samples)


def write_capture_csv(path, samples, times_s, meta):
    """Write one capture; return the number of data rows.

    ``#``-prefixed ``key=value`` preamble (``pandas.read_csv(p, comment="#")``
    skips it), then ``index,t_s,counts,volts,amps``. Volts and amps are
    derived here so the file stands alone; raw counts stay in their own
    column so a different Vref/Rf can be re-applied later. Rows are
    streamed, never joined — a long capture is millions of rows.
    """
    full_scale = float(meta.get("adc_full_scale") or 1.0)
    vref = float(meta.get("vref_v") or 0.0)
    rf = float(meta.get("rf_ohms") or 0.0)
    scale_v = vref / full_scale
    with open(path, "w", newline="") as fh:
        for key, value in meta.items():
            clean = str(value).replace("\r", " ").replace("\n", " ")
            fh.write(f"# {key}={clean}\n")
        fh.write("index,t_s,counts,volts,amps\n")
        for i, counts in enumerate(samples):
            t = times_s[i] if i < len(times_s) else i / 1000.0
            volts = counts * scale_v
            amps = volts / rf if rf else 0.0
            fh.write(f"{i},{t:.6f},{counts},{volts:.9f},{amps:.12e}\n")
    return len(samples)


def capture_filename(kind, gain, now=None):
    """``pmt_<kind>_<YYYYmmdd-HHMMSS>_gain<gain>.csv``.

    The capture routine passes ``f"spot{slot}"`` (unchanged from before
    ``kind`` existed); the buffered acquire passes ``"acquire"``.
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"pmt_{kind}_{stamp}_gain{gain}.csv"


def decode_pmt_positions(reply):
    """Decode a ``GET_PARAMS`` reply for ``pmt_defaults`` into spot positions.

    The reply echoes the flash key, a NUL, then the raw struct: big-endian
    int32 Y-axis positions in µm, one per motor location (the driver's
    ``PMTPositionParams``). Location 1 is park and is dropped, so index 0 of
    the result is spot 1 (location 2). A five-location table from older
    firmware is zero-padded, as the driver itself does, so its missing last
    spot reads as unused.
    """
    raw = bytes(reply)
    blob = raw.split(b"\x00", 1)[1] if b"\x00" in raw else raw

    if len(blob) < _LEGACY_POSITIONS_BYTES:
        raise ValueError(
            f"PMT position table is {len(blob)} bytes, "
            f"expected at least {_LEGACY_POSITIONS_BYTES}"
        )

    positions = _POSITIONS.unpack_from(blob.ljust(_POSITIONS.size, b"\x00"))

    return list(positions[PMT_PARK_LOCATION:])
