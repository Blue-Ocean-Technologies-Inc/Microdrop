# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater-log reading for the temperature x-axis: the heater plugin
writes 1 Hz JSONL logs (``TEMP`` lines carrying {sensor: °C}) on the
same wall clock the captures are stamped with, so time is the join
key. Pure file/number logic, Qt-free."""

# Standard library imports.
import bisect
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path

# Local imports.
from .consts import HEATER_SAMPLE_MARGIN_S, HEATER_SENSOR_MEAN

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The stamp a heater log is named by (its first line's local time).
HEATER_LOG_STAMP_PATTERN = re.compile(r"\d{8}_\d{6}")
HEATER_LOG_STAMP_FORMAT = "%Y%m%d_%H%M%S"


def _file_start(path):
    """Epoch seconds of the stamp in a heater log's name — the LOCAL
    clock, which is what the logger writes — or None for a name
    without one (which then cannot be placed in time)."""
    match = HEATER_LOG_STAMP_PATTERN.search(Path(path).stem)
    if not match:
        return None
    try:
        return time.mktime(time.strptime(match.group(0), HEATER_LOG_STAMP_FORMAT))
    except (ValueError, OverflowError):
        return None


def heater_log_files(folder, start_epoch, end_epoch):
    """The folder's ``*.jsonl`` logs overlapping the capture range
    (±HEATER_SAMPLE_MARGIN_S), ordered by name stamp. A log covers
    from its own stamp until the next one begins; the last runs
    open-ended, since nothing marks where it stopped."""
    try:
        stamped = sorted(
            (stamp, path)
            for path in Path(folder).glob("*.jsonl")
            if (stamp := _file_start(path)) is not None
        )
    except OSError:
        return []
    low = start_epoch - HEATER_SAMPLE_MARGIN_S
    high = end_epoch + HEATER_SAMPLE_MARGIN_S
    chosen = []
    for index, (stamp, path) in enumerate(stamped):
        until = stamped[index + 1][0] if index + 1 < len(stamped) else math.inf
        if stamp <= high and until >= low:
            chosen.append(path)
    return chosen


def read_heater_samples(folder, start_epoch, end_epoch):
    """``[(epoch, {sensor: °C}), ...]`` sorted by time, from the
    folder's logs overlapping the capture range. Only ``TEMP`` lines
    count; their naive ISO timestamp is the local clock. A malformed
    line is skipped, not a reason to drop its file; a missing or
    empty folder is simply no samples."""
    low = start_epoch - HEATER_SAMPLE_MARGIN_S
    high = end_epoch + HEATER_SAMPLE_MARGIN_S
    samples = []
    for path in heater_log_files(folder, start_epoch, end_epoch):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            logger.warning(f"Unreadable heater log {path}: {error}")
            continue
        for line in lines:
            try:
                record = json.loads(line)
                if record.get("_frame") != "TEMP":
                    continue
                epoch = datetime.fromisoformat(record["timestamp"]).timestamp()
                temperatures = {
                    str(name): float(value)
                    for name, value in record["temperatures"].items()
                }
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if temperatures and low <= epoch <= high:
                samples.append((epoch, temperatures))
    samples.sort(key=lambda sample: sample[0])
    return samples


def sensors_in(samples):
    """Sorted sensor names appearing anywhere in ``samples``."""
    names = set()
    for _epoch, temperatures in samples:
        names.update(temperatures)
    return sorted(names)


def _sensor_value(temperatures, sensor):
    if sensor == HEATER_SENSOR_MEAN:
        return sum(temperatures.values()) / len(temperatures)
    value = temperatures.get(sensor)
    return math.nan if value is None else value


def temperature_at(samples, sensor, epochs, window_s=0.0):
    """``sensor``'s temperature at each epoch. With a ``window_s``,
    the mean of every sample within ±window_s/2 — the user's say on
    how generous the match in time may be — and NaN when none falls
    inside (a too-narrow window near a logger dropout is a gap, not
    a guess). With none, linear interpolation at the instant — NaN
    outside the sampled range (an extrapolated temperature would be
    invented data) or where no sample carries the sensor."""
    pairs = [
        (epoch, value)
        for epoch, temperatures in samples
        if (value := _sensor_value(temperatures, sensor)) == value
    ]
    times = [epoch for epoch, _value in pairs]
    half = window_s / 2.0
    results = []
    for query in epochs:
        if not pairs:
            results.append(math.nan)
            continue
        if window_s > 0:
            low = bisect.bisect_left(times, query - half)
            high = bisect.bisect_right(times, query + half)
            inside = [value for _epoch, value in pairs[low:high]]
            results.append(sum(inside) / len(inside) if inside else math.nan)
            continue
        if query < times[0] or query > times[-1]:
            results.append(math.nan)
            continue
        index = bisect.bisect_left(times, query)
        if index < len(times) and times[index] == query:
            results.append(pairs[index][1])
            continue
        (left_time, left), (right_time, right) = (pairs[index - 1], pairs[index])
        span = right_time - left_time
        results.append(
            left if span <= 0 else left + (right - left) * (query - left_time) / span
        )
    return results
