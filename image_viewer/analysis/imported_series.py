# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Series of the plotted experiments other than the live one: each run
read from disk, measured and corrected by the live experiment's figure
settings over its own ROIs and exclusions, keyed apart from the live
ROIs, on the live x axis — so the plot draws them as it draws its own.
Qt-free."""

# Standard library imports.
import math
from pathlib import Path

# Local imports.
from .consts import (
    IMPORTED_KEY_SEPARATOR,
    IMPORTED_NAME_SEPARATOR,
    TIME_UNIT_PER_SECOND,
)
from .plot_series import analysed_and_excluded_series, time_origin


def measured_paths(session):
    """The images ``session``'s stats store holds a measurement of —
    what that experiment analysed, through whatever image filter it was
    measured under — oldest first (by the mtime each was measured at,
    then name, as discovery orders captures), each spelled as its key
    spells it, so cache_key finds it again."""
    measured_at = {}

    for key in session.stats:
        path, mtime = key[0], key[1]
        measured_at[path] = max(mtime, measured_at.get(path, mtime))

    return sorted(measured_at, key=lambda path: (measured_at[path], Path(path).name))


def run_paths(session):
    """The images of ``session``'s run the plot reads, oldest first by
    capture time: every one its stats store measured (measured_paths)
    and every one its analysis excluded found beside them — so its
    excluded points are drawn, and its time axis spans the whole run,
    as the live experiment's are."""
    measured = measured_paths(session)
    folders = list(dict.fromkeys(Path(path).parent for path in measured))
    known = {Path(path).name for path in measured}
    excluded = []

    for name in session.excluded_images:
        found = next(
            (folder / name for folder in folders if (folder / name).is_file()), None
        )

        if name not in known and found is not None:
            excluded.append(str(found))

    stat_cache = {}

    return sorted(
        measured + excluded,
        key=lambda path: (session.stat_info(path, stat_cache)[1], Path(path).name),
    )


def imported_key(directory, roi_id):
    """The curve key of the ROI ``roi_id`` of the experiment imported
    from ``directory``."""
    return f"{directory}{IMPORTED_KEY_SEPARATOR}{roi_id}"


def split_imported_key(key):
    """(folder, roi_id) of an imported_key; ("", ``key``) for a current
    ROI's id."""
    directory, separator, roi_id = key.rpartition(IMPORTED_KEY_SEPARATOR)

    return (directory, roi_id) if separator else ("", key)


def run_offset(primary, primary_paths, other, other_paths):
    """The x shift putting ``other``'s run on ``primary``'s clock: its
    time origin less the current one's, in the figure's time unit, on
    the elapsed-time axis — and 0 on every other, where frames and
    steps number each run from its own start and a temperature is the
    same temperature in any run. 0 too when either run has no image."""
    figure = primary.figure

    if figure.x_axis != "time" or not primary_paths or not other_paths:
        return 0.0

    per_second = TIME_UNIT_PER_SECOND[figure.time_unit]
    shift = time_origin(other, other_paths) - time_origin(primary, primary_paths)

    return shift * per_second


def _rekeyed(curves, directory, label, offset):
    """``curves`` ({roi_id: (name, [x], [value])}) keyed by imported_key,
    named "<label> · <name>" and shifted ``offset`` along x."""
    return {
        imported_key(directory, roi_id): (
            f"{label}{IMPORTED_NAME_SEPARATOR}{name}",
            [x + offset for x in x_values],
            values,
        )
        for roi_id, (name, x_values, values) in curves.items()
    }


def imported_series(
    primary, primary_paths, other, other_paths, label, align_to_run_start
):
    """(series, outlier flags, excluded, area fit) — what
    analysed_and_excluded_series gives the current experiment — of the
    imported experiment ``other`` (its loaded session, over its
    ``other_paths``) as ``primary`` plots it: ``primary``'s figure and
    plot stat over ``other``'s own ROIs (each shown while its own eye
    is), stats, exclusions, background references and calibration.
    Each is keyed by imported_key, each curve named
    "<label> · <ROI name>".

    x is relative to each run's own start while ``align_to_run_start``,
    else on the current run's clock (see run_offset). ``other`` takes
    ``primary``'s figure and plot stat in place: it is a read-only copy
    nothing saves."""
    other.trait_set(figure=primary.figure, plot_stat=primary.plot_stat)
    series, flags, excluded, area_fit = analysed_and_excluded_series(other, other_paths)
    offset = 0.0

    if not align_to_run_start:
        offset = run_offset(primary, primary_paths, other, other_paths)

    directory = other.directory
    keyed_flags = {
        imported_key(directory, roi_id): roi_flags
        for roi_id, roi_flags in flags.items()
    }

    return (
        _rekeyed(series, directory, label, offset),
        keyed_flags,
        _rekeyed(excluded, directory, label, offset),
        _rekeyed(area_fit, directory, label, offset),
    )


def _cell(value):
    """``value`` as a spreadsheet cell: blank where it is NaN."""
    return "" if value is None or value != value else repr(float(value))


def series_table(series, x_label):
    """Tab-separated text of ``series`` ({key: (name, [x], [value])}),
    a spreadsheet's paste: an x and a value column per curve — the
    curves need not share their x — headed "<name> <x_label>" and
    "<name>", a row per point to the longest curve, blank where a curve
    has no point or a value is NaN."""
    entries = list(series.values())
    header = []

    for name, _x_values, _values in entries:
        header += [f"{name} {x_label}", name]

    rows = ["\t".join(header)]
    length = max((len(x_values) for _name, x_values, _values in entries), default=0)

    for index in range(length):
        cells = []

        for _name, x_values, values in entries:
            within = index < len(x_values)
            cells += [
                _cell(x_values[index] if within else math.nan),
                _cell(values[index] if within else math.nan),
            ]

        rows.append("\t".join(cells))

    return "\n".join(rows) + "\n"
