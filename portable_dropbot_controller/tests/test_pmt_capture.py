# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the PMT capture helpers: stream packet assembly, cadence
calibration, stats, the bench-compatible CSV, and the position-table decode.
Pure functions, no driver, no hardware."""

# Standard library imports.
import csv
import struct
from datetime import datetime

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.pmt_capture import (
    StreamAssembler,
    calibrate_period,
    capture_filename,
    capture_stats,
    decode_pmt_positions,
    write_capture_csv,
)


def _packet(idx, values):
    return struct.pack("<HH", idx, len(values)) + struct.pack(
        f"<{len(values)}H", *values
    )


def test_assembler_keeps_samples_in_packet_order():
    a = StreamAssembler()
    assert a.feed(0x123F, _packet(0, [1, 2, 3]), now=0.0) is True
    assert a.feed(0x123F, _packet(1, [4, 5, 6]), now=0.1) is True
    samples, index, arrivals = a.snapshot()
    assert samples == [1, 2, 3, 4, 5, 6]
    assert index == [0, 1, 2, 3, 4, 5]
    assert arrivals == [(0, 0.0), (1, 0.1)]
    assert a.packets == 2 and a.duplicates == 0 and a.samples_per_packet == 3


def test_assembler_survives_u16_wrap_and_drops_duplicates():
    a = StreamAssembler()
    a.feed(0x123F, _packet(65535, [7]), now=0.0)
    a.feed(0x123F, _packet(0, [8]), now=0.1)  # wrap -> abs index 65536
    assert a.feed(0x123F, _packet(0, [9]), now=0.2) is False  # duplicate
    samples, index, arrivals = a.snapshot()
    assert samples == [7, 8]
    assert index == [0, 1]
    assert [abs_idx for abs_idx, _ in arrivals] == [65535, 65536]
    assert a.duplicates == 1


def test_assembler_ignores_short_or_empty_frames():
    a = StreamAssembler()
    assert a.feed(0x123F, b"\x00\x01", now=0.0) is False
    assert a.feed(0x123F, struct.pack("<HH", 0, 0), now=0.0) is False
    assert a.feed(0x123F, struct.pack("<HH", 0, 4) + b"\x00\x00", now=0.0) is False
    assert a.packets == 0


def test_calibrate_period_measures_cadence_when_plausible():
    a = StreamAssembler()
    for i in range(4):
        a.feed(0x123F, _packet(i, [0] * 62), now=i * 62 * 0.023)  # 23 ms per value
    period, source = calibrate_period(a, avg=16)
    assert source == "measured"
    assert period == pytest.approx(0.023)


def test_calibrate_period_falls_back_to_estimate():
    a = StreamAssembler()
    assert calibrate_period(a, avg=16) == (0.016, "estimated")  # no packets
    a.feed(0x123F, _packet(0, [0] * 62), now=0.0)
    a.feed(0x123F, _packet(1, [0] * 62), now=0.0)  # burst arrival -> implausible
    period, source = calibrate_period(a, avg=16)
    assert (period, source) == (0.016, "estimated")


def test_capture_stats():
    assert capture_stats([]) == (0, 0.0, 0.0, 0, 0)
    assert capture_stats([5]) == (1, 5.0, 0.0, 5, 5)
    n, mean, sd, lo, hi = capture_stats([2, 4, 4, 4, 5, 5, 7, 9])
    assert (n, mean, lo, hi) == (8, 5.0, 2, 9)
    assert sd == pytest.approx(2.138, abs=1e-3)  # sample sd


def test_write_capture_csv_preamble_and_columns(tmp_path):
    path = tmp_path / "x.csv"
    meta = {
        "source": "test",
        "adc_full_scale": 65536,
        "vref_v": 4.98,
        "rf_ohms": 499000.0,
        "note": "line1\nline2",
    }
    assert write_capture_csv(path, [0, 32768], [0.0, 0.023], meta) == 2
    lines = path.read_text().splitlines()
    assert lines[0] == "# source=test"
    assert "# note=line1 line2" in lines
    header_at = lines.index("index,t_s,counts,volts,amps")
    rows = list(csv.DictReader(lines[header_at:]))
    assert [r["counts"] for r in rows] == ["0", "32768"]
    assert float(rows[1]["volts"]) == pytest.approx(32768 * 4.98 / 65536)
    assert float(rows[1]["amps"]) == pytest.approx(32768 * 4.98 / 65536 / 499000.0)
    assert float(rows[1]["t_s"]) == pytest.approx(0.023)


def test_capture_filename():
    now = datetime(2026, 9, 8, 14, 5, 9)
    assert capture_filename(3, 128, now) == "pmt_spot3_20260908-140509_gain128.csv"


def test_decode_pmt_positions_reads_five_big_endian_int32_after_the_key():
    blob = struct.pack(">5i", 1000, 24500, 0, 61000, -5)
    assert decode_pmt_positions(b"_dp_pmt\x00" + blob + b"trailing") == [
        1000,
        24500,
        0,
        61000,
        -5,
    ]
    with pytest.raises(ValueError):
        decode_pmt_positions(b"_dp_pmt\x00" + blob[:8])
