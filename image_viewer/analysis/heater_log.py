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
key. Pure file/number logic, Qt-free. HeaterLogReader is the
incremental reader for a log the heater is still writing: it parses
only the bytes appended since its last read."""

# Standard library imports.
import bisect
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path

# Enthought library imports.
from traits.api import Any, Dict, HasTraits, Instance, Int, List, Str, Tuple

# Local imports.
from .consts import (
    HEATER_LOGS_DIR_NAME,
    HEATER_SAMPLE_MARGIN_S,
    HEATER_SENSOR_MEAN,
    HEATER_SIBLING_SEARCH_LIMIT,
)

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


def _stamped_logs(folder):
    """``[(stamp epoch, path), ...]`` of the folder's ``*.jsonl`` logs
    that carry a name stamp, oldest first; empty for a missing folder."""
    try:
        return sorted(
            (stamp, path)
            for path in Path(folder).glob("*.jsonl")
            if (stamp := _file_start(path)) is not None
        )
    except OSError:
        return []


def _sample_epoch(line):
    """Epoch of a ``TEMP`` log line, or None for any other line."""
    try:
        record = json.loads(line)

        if record.get("_frame") != "TEMP":
            return None

        return datetime.fromisoformat(record["timestamp"]).timestamp()

    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _parse_temp_line(line):
    """``(epoch, {sensor: °C})`` of a ``TEMP`` log line — the readings
    None when they are malformed, though the time still counts toward
    the log's span — or None for any other line."""

    try:
        record = json.loads(line)

        if record.get("_frame") != "TEMP":
            return None

        epoch = datetime.fromisoformat(record["timestamp"]).timestamp()

    except (ValueError, KeyError, TypeError, AttributeError):
        return None

    try:
        temperatures = {
            str(name): float(value) for name, value in record["temperatures"].items()
        }

    except (ValueError, KeyError, TypeError, AttributeError):
        temperatures = None

    return epoch, temperatures


def _is_json(text):
    """Whether ``text`` parses as one whole JSON value."""

    try:
        json.loads(text)

    except ValueError:
        return False

    return True


def heater_log_span(folder):
    """``(first, last)`` epochs the folder's logs cover — the oldest
    name stamp to the newest log's last ``TEMP`` line — or None when
    the folder holds no stamped log. Only the newest log is read: it
    is the open-ended one whose end the stamps cannot tell."""
    stamped = _stamped_logs(folder)

    if not stamped:
        return None

    first = stamped[0][0]
    newest_stamp, newest_path = stamped[-1]

    try:
        lines = newest_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        logger.warning(f"Unreadable heater log {newest_path}: {error}")
        lines = []

    last = next(
        (
            epoch
            for line in reversed(lines)
            if (epoch := _sample_epoch(line)) is not None
        ),
        newest_stamp,
    )

    return first, max(first, last)


def _overlap_s(span, start_epoch, end_epoch):
    """Seconds a log span shares with the capture range
    (±HEATER_SAMPLE_MARGIN_S); negative when they are apart."""
    low = start_epoch - HEATER_SAMPLE_MARGIN_S
    high = end_epoch + HEATER_SAMPLE_MARGIN_S

    return min(high, span[1]) - max(low, span[0])


def sibling_heater_log_spans(experiment_directory, limit=HEATER_SIBLING_SEARCH_LIMIT):
    """``[(heater_logs folder, span), ...]`` of the ``limit`` most
    recently modified sibling experiments with a heater_logs folder,
    newest first — those without a stamped log left out. The costly
    half of the sibling search (it reads each sibling's newest log),
    independent of the capture range."""
    experiment = Path(experiment_directory)

    try:
        siblings = [
            path
            for path in experiment.parent.iterdir()
            if path.name != experiment.name and (path / HEATER_LOGS_DIR_NAME).is_dir()
        ]
        siblings.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    except OSError as error:
        logger.warning(f"Could not list experiments beside {experiment}: {error}")
        return []

    spans = []

    for sibling in siblings[:limit]:
        folder = sibling / HEATER_LOGS_DIR_NAME
        span = heater_log_span(folder)

        if span is not None:
            spans.append((folder, span))

    return spans


def overlapping_siblings(sibling_spans, start_epoch, end_epoch):
    """``[(heater_logs folder, overlap s), ...]`` of the
    sibling_heater_log_spans() entries overlapping the capture range,
    most overlap first."""
    matches = []

    for folder, span in sibling_spans:
        overlap = _overlap_s(span, start_epoch, end_epoch)

        if overlap >= 0:
            matches.append((folder, overlap))

    matches.sort(key=lambda match: match[1], reverse=True)

    return matches


def sibling_heater_log_folders(
    experiment_directory, start_epoch, end_epoch, limit=HEATER_SIBLING_SEARCH_LIMIT
):
    """``[(heater_logs folder, overlap s), ...]`` of the sibling
    experiments whose heater logs overlap the capture range, most
    overlap first. Only the ``limit`` most recently modified siblings
    with a heater_logs folder are searched, newest first."""
    return overlapping_siblings(
        sibling_heater_log_spans(experiment_directory, limit), start_epoch, end_epoch
    )


def resolve_heater_samples(folder, experiment_directory, start_epoch, end_epoch):
    """``(samples, fallback folder, match count)`` for the capture
    range: the configured folder's samples, or — when it has none in
    range and is the experiment's default heater_logs folder — those
    of the sibling experiment whose logs overlap the range most. A
    folder the user picked is respected, covered or not. The fallback
    folder is "" when the configured one served; it is only ever
    reported, never a replacement for the user's choice."""
    samples = read_heater_samples(folder, start_epoch, end_epoch)

    if samples or experiment_directory is None:
        return samples, "", 0

    if Path(folder) != Path(experiment_directory) / HEATER_LOGS_DIR_NAME:
        return samples, "", 0

    matches = sibling_heater_log_folders(experiment_directory, start_epoch, end_epoch)

    for sibling, _overlap in matches:
        samples = read_heater_samples(sibling, start_epoch, end_epoch)

        if samples:
            return samples, str(sibling), len(matches)

    return [], "", 0


def _clock_range(first, last, reference_epoch):
    """``first–last`` as wall-clock times; a time on another day than
    ``reference_epoch`` carries its date, so a stale log reads as one."""
    reference_day = time.localtime(reference_epoch)[:3]
    clocks = []

    for epoch in (first, last):
        moment = time.localtime(epoch)
        same_day = moment[:3] == reference_day
        clocks.append(
            time.strftime("%H:%M:%S" if same_day else "%Y-%m-%d %H:%M", moment)
        )

    return "–".join(clocks)


def describe_heater_coverage(
    searched_folder, log_span, capture_span, fallback_folder="", match_count=0
):
    """One line on where the temperature axis looked and what it found:
    the folder searched, its log span (or that it has no logs), the
    capture span, and — when a sibling experiment's logs stood in —
    which experiment they came from."""
    start, end = capture_span
    searched = Path(searched_folder)
    found = (
        "no heater log files"
        if log_span is None
        else f"logs {_clock_range(*log_span, start)}"
    )
    detail = (
        f"searched {searched.parent.name}/{searched.name}: {found}; "
        f"captures {_clock_range(start, end, start)}"
    )

    if not fallback_folder:
        return detail

    using = f"using logs from {Path(fallback_folder).parent.name}"

    if match_count > 1:
        using += f" (most overlap of {match_count} matches)"

    return f"{using} — {detail}"


def heater_coverage_note(missing, coverage, fallback_used):
    """The plot's note on the heater join: how many frames have no
    temperature, then the coverage line explaining why — or, when a
    sibling's logs covered every frame, that line alone so the borrowed
    source stays visible. "" when there is nothing to say."""
    if not missing and not fallback_used:
        return ""

    lines = []

    if missing:
        noun = "frame" if missing == 1 else "frames"
        lines.append(f"{missing} {noun} outside the heater log's coverage")

    if coverage:
        lines.append(coverage)

    return "\n".join(lines)


def heater_log_files(folder, start_epoch, end_epoch):
    """The folder's ``*.jsonl`` logs overlapping the capture range
    (±HEATER_SAMPLE_MARGIN_S), ordered by name stamp. A log covers
    from its own stamp until the next one begins; the last runs
    open-ended, since nothing marks where it stopped."""
    return _overlapping_logs(_stamped_logs(folder), start_epoch, end_epoch)


def _overlapping_logs(stamped, start_epoch, end_epoch):
    """heater_log_files() over an already-listed ``_stamped_logs()``."""
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
            parsed = _parse_temp_line(line)

            if parsed is None:
                continue

            epoch, temperatures = parsed

            if temperatures and low <= epoch <= high:
                samples.append(parsed)

    samples.sort(key=lambda sample: sample[0])

    return samples


class TailedHeaterLog(HasTraits):
    """One heater log read incrementally: each read() parses only the
    bytes appended since the last, so a log the heater is still writing
    costs its new lines rather than its whole length."""

    #: The log file.
    path = Instance(Path)

    #: Bytes consumed so far — always the end of a whole line.
    offset = Int(0)

    #: Every ``TEMP`` sample with readings, in file order:
    #: [(epoch, {sensor: °C}), ...].
    samples = List()

    #: Epoch of the last ``TEMP`` line read, readings or not — where the
    #: log ends for its span; None before one is read.
    last_epoch = Any(None)

    def read(self):
        """Parse whatever was appended since the last read. A file
        shorter than what was already consumed was truncated or
        replaced, so it is read again from the start."""

        try:
            size = self.path.stat().st_size

        except OSError as error:
            logger.warning(f"Unreadable heater log {self.path}: {error}")
            return

        if size < self.offset:
            logger.info(f"Heater log {self.path.name} shrank; reading it afresh")
            self.trait_set(offset=0, samples=[], last_epoch=None)

        if size == self.offset:
            return

        try:
            with self.path.open("rb") as stream:
                stream.seek(self.offset)
                chunk = stream.read(size - self.offset)

        except OSError as error:
            logger.warning(f"Unreadable heater log {self.path}: {error}")
            return

        lines = chunk.split(b"\n")
        fragment = lines.pop()
        consumed = len(chunk) - len(fragment)

        # The writer may be mid-line: an unterminated tail is taken only
        # once it parses whole, else it waits for the next read.
        if fragment.strip() and _is_json(fragment):
            lines.append(fragment)
            consumed = len(chunk)

        appended = []
        last_epoch = self.last_epoch

        for line in lines:
            parsed = _parse_temp_line(line)

            if parsed is None:
                continue

            last_epoch, temperatures = parsed

            if temperatures:
                appended.append(parsed)

        self.samples.extend(appended)
        self.trait_set(offset=self.offset + consumed, last_epoch=last_epoch)


class HeaterSamples(HasTraits):
    """What one HeaterLogReader.resolve() found for a capture range."""

    #: The folder searched (the session's heater_log_dir).
    folder = Str()

    #: (start, end) epochs of the captures the samples were sought for.
    capture_span = Tuple(0.0, 0.0)

    #: [(epoch, {sensor: °C}), ...] within the range, sorted by time.
    samples = List()

    #: The sibling experiment's heater_logs folder that stood in, ""
    #: when the searched folder served.
    fallback = Str()

    #: How many siblings overlapped the range when one stood in.
    match_count = Int(0)

    #: heater_log_span() of the searched folder, None without a log.
    span = Any(None)

    #: What was read — folder, fallback, range and (log, offset) pairs —
    #: equal for two resolves that saw the same bytes.
    fingerprint = Any(None)


class HeaterLogReader(HasTraits):
    """resolve_heater_samples() made incremental: every log is tailed
    (TailedHeaterLog), and the sibling-experiment spans are searched
    once per experiment, so asking again as captures arrive costs the
    newly written lines. Not thread-safe: one thread at a time."""

    #: path str -> its tail, for every log read so far.
    _logs = Dict(Str, Instance(TailedHeaterLog))

    #: experiment directory str -> its sibling_heater_log_spans().
    _sibling_spans = Dict(Str, List)

    def resolve(self, folder, experiment_directory, start_epoch, end_epoch):
        """HeaterSamples for the capture range, by the same rules as
        resolve_heater_samples(), with the searched folder's span."""
        read_state = []
        samples, span = self._folder_samples(folder, start_epoch, end_epoch, read_state)
        fallback = ""
        match_count = 0
        default_folder = (
            experiment_directory is not None
            and Path(folder) == Path(experiment_directory) / HEATER_LOGS_DIR_NAME
        )

        if not samples and default_folder:
            matches = overlapping_siblings(
                self._siblings_of(experiment_directory), start_epoch, end_epoch
            )

            for sibling, _overlap in matches:
                sibling_samples, _span = self._folder_samples(
                    sibling, start_epoch, end_epoch, read_state
                )

                if sibling_samples:
                    samples = sibling_samples
                    fallback = str(sibling)
                    match_count = len(matches)
                    break

        return HeaterSamples(
            folder=str(folder),
            capture_span=(start_epoch, end_epoch),
            samples=samples,
            fallback=fallback,
            match_count=match_count,
            span=span,
            fingerprint=(
                str(folder),
                fallback,
                round(start_epoch),
                round(end_epoch),
                tuple(read_state),
            ),
        )

    def _folder_samples(self, folder, start_epoch, end_epoch, read_state):
        """``(samples, span)`` — read_heater_samples() and
        heater_log_span() from one listing and one tail of the logs
        involved — appending (log, offset) pairs to ``read_state``."""
        stamped = _stamped_logs(folder)

        if not stamped:
            return [], None

        overlapping = _overlapping_logs(stamped, start_epoch, end_epoch)
        newest_stamp, newest_path = stamped[-1]
        low = start_epoch - HEATER_SAMPLE_MARGIN_S
        high = end_epoch + HEATER_SAMPLE_MARGIN_S
        samples = []

        # The newest log is tailed even outside the range: its last line
        # is where the folder's span ends.
        for path in dict.fromkeys(overlapping + [newest_path]):
            log = self._tail(path)
            log.read()
            read_state.append((str(path), log.offset))

            if path in overlapping:
                samples.extend(
                    sample for sample in log.samples if low <= sample[0] <= high
                )

        samples.sort(key=lambda sample: sample[0])
        first = stamped[0][0]
        last = self._tail(newest_path).last_epoch

        return samples, (first, max(first, newest_stamp if last is None else last))

    def _tail(self, path):
        key = str(path)

        if key not in self._logs:
            self._logs[key] = TailedHeaterLog(path=Path(path))

        return self._logs[key]

    def _siblings_of(self, experiment_directory):
        key = str(experiment_directory)

        if key not in self._sibling_spans:
            self._sibling_spans[key] = sibling_heater_log_spans(experiment_directory)

        return self._sibling_spans[key]


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
