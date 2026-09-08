# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure helpers for the portable PMT capture routine.

Ported from the driver repo's bench UI (``full_test_ui/tabs/pmt_tab.py``)
so the CSVs Microdrop writes are interchangeable with the bench's. No Qt,
no driver import: everything here is unit-testable without hardware.

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
from .consts import PMT_SPOT_SLOTS

#: Absolute-index step that reads as a u16 counter wrap rather than a
#: duplicated/aliased frame.
_WRAP_THRESHOLD = 0x8000
_HEADER = struct.Struct("<HH")
_POSITIONS = struct.Struct(f">{PMT_SPOT_SLOTS}i")


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
        if len(data) < _HEADER.size:
            return False
        idx, n = _HEADER.unpack_from(data)
        if not n or len(data) < _HEADER.size + 2 * n:
            return False
        values = struct.unpack_from(f"<{n}H", data, _HEADER.size)
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


def capture_filename(slot, gain, now=None):
    """``pmt_spot<slot>_<YYYYmmdd-HHMMSS>_gain<gain>.csv``."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"pmt_spot{slot}_{stamp}_gain{gain}.csv"


def decode_pmt_positions(reply):
    """Decode a ``GET_PARAMS`` reply for ``pmt_defaults`` into slot positions.

    The reply echoes the flash key, a NUL, then the raw struct: five
    big-endian int32 Y-axis positions in µm (the driver's
    ``PMTPositionParams`` layout), index 0 = slot 1.
    """
    raw = bytes(reply)
    blob = raw.split(b"\x00", 1)[1] if b"\x00" in raw else raw
    if len(blob) < _POSITIONS.size:
        raise ValueError(
            f"PMT position table is {len(blob)} bytes, expected {_POSITIONS.size}"
        )
    return list(_POSITIONS.unpack_from(blob))
