# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Persistence for the ROI analysis: the per-experiment session config
(roi_config.json v2 — ROIs with styles, plot stat, figure settings),
the computed-stats store (roi_stats.json), and the intensity CSV
export. Qt-free, pure file IO."""

# Standard library imports.
import csv
import json
import math
from pathlib import Path

# Local imports.
from .consts import (
    ANALYSIS_DIR_NAME,
    FIT_EQUATIONS_FILENAME,
    OUTLINE_STATS_PREFIX,
    ROI_CONFIG_FILENAME,
    ROI_STATS_FILENAME,
)
from .plot_series import normalized_series, stat_value
from .roi_compute import STAT_NAMES
from .roi_geometry import normalize
from .roi_model import (
    AnalysisSession,
    BackgroundRing,
    FigureSettings,
    PerspectiveCorrection,
    Roi,
    RoiStyle,
    RollingBall,
    ScaleCalibration,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Persisted FigureSettings fields (also the tolerated-missing set on
#: load, so older configs upgrade with defaults).
_FIGURE_FIELDS = (
    "x_auto",
    "x_min",
    "x_max",
    "y_auto",
    "y_min",
    "y_max",
    "export_format",
    "export_dpi",
    "fit_method",
    "custom_expression",
    "initial_guesses",
    "trim_poor_fit",
    "show_legend",
    "show_fit_equations",
    "show_second_derivative_max",
    "show_second_derivative_min",
    "second_derivative_vline",
    "second_derivative_hline",
    "second_derivative_coords",
    "view_mode",
    "log_x",
    "log_y",
    "normalize",
    "subtract_first",
    "subtract_background_ref",
    "remove_outliers",
    "outlier_threshold",
    "outlier_window",
    "interpolate_gaps",
    "smooth_method",
    "savgol_window",
    "savgol_order",
    "butter_order",
    "butter_cutoff",
    "x_axis",
    "heater_sensor",
    "heater_window_ms",
    "show_method_group",
    "show_metrics_group",
)
_STYLE_FIELDS = ("color", "line_style", "marker", "marker_size", "visible", "alpha")

#: Persisted ScaleCalibration fields (tolerated-missing on load, so a
#: config written before the scale bar opens uncalibrated).
_SCALE_FIELDS = ("metres_per_pixel", "value", "unit")

#: Persisted BackgroundRing fields (tolerated-missing on load).
_RING_FIELDS = ("gap_px", "thickness_px", "show_on_canvas")

#: Persisted RollingBall fields (tolerated-missing on load, so a config
#: written before the ball existed opens with it off).
_BALL_FIELDS = ("enabled", "radius_px", "show_reference")

#: Persisted PerspectiveCorrection fields (tolerated-missing on load, so a
#: config written before the correction existed opens without one).
_PERSPECTIVE_FIELDS = ("enabled", "source_quad", "target_quad")


def analysis_directory(experiment_directory) -> Path:
    """The experiment's analysis output folder, created on demand."""
    directory = Path(experiment_directory) / ANALYSIS_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_session(experiment_directory, session):
    payload = {
        "version": 2,
        "plot_stat": session.plot_stat,
        "heater_log_dir": session.heater_log_dir,
        "figure": {name: getattr(session.figure, name) for name in _FIGURE_FIELDS},
        "scale": {name: getattr(session.scale, name) for name in _SCALE_FIELDS},
        "ring": {name: getattr(session.ring, name) for name in _RING_FIELDS},
        "ball": {name: getattr(session.ball, name) for name in _BALL_FIELDS},
        "perspective": {
            name: getattr(session.perspective, name) for name in _PERSPECTIVE_FIELDS
        },
        "excluded_images": list(session.excluded_images),
        "rois": [
            {
                "roi_id": roi.roi_id,
                "name": roi.name,
                "kind": roi.kind,
                "geometry": list(roi.geometry),
                "base_anchor": roi.base_anchor,
                "overrides": {
                    repr(anchor): list(geometry)
                    for anchor, geometry in roi.overrides.items()
                },
                "style": {name: getattr(roi.style, name) for name in _STYLE_FIELDS},
                "is_background_ref": roi.is_background_ref,
            }
            for roi in session.rois
        ],
    }
    path = analysis_directory(experiment_directory) / ROI_CONFIG_FILENAME
    path.write_text(json.dumps(payload, indent=2))


def _roi_from(entry):
    style = RoiStyle()
    style.trait_set(
        **{
            name: entry.get("style", {})[name]
            for name in _STYLE_FIELDS
            if name in entry.get("style", {})
        }
    )
    kind, geometry = normalize(entry["kind"], entry["geometry"])
    return Roi(
        roi_id=entry["roi_id"],
        name=entry["name"],
        kind=kind,
        geometry=geometry,
        base_anchor=float(entry["base_anchor"]),
        overrides={
            float(anchor): normalize(kind, override)[1]
            for anchor, override in entry["overrides"].items()
        },
        # "is_standard" is what this was called before the
        # rename, and absent entirely in configs written before
        # the feature — where no ROI was one either way.
        is_background_ref=bool(
            entry.get("is_background_ref", entry.get("is_standard", False))
        ),
        style=style,
    )


def load_session(experiment_directory) -> AnalysisSession:
    """The experiment's saved analysis session; empty (with defaults)
    when absent or unreadable. Accepts the v1 format (a bare ROI list,
    no styles/figure) with defaults filling the rest. One bad ROI entry
    or an invalid plot_stat/figure value is skipped/defaulted in place
    rather than discarding every other ROI already parsed."""
    session = AnalysisSession(directory=str(experiment_directory))
    path = Path(experiment_directory) / ANALYSIS_DIR_NAME / ROI_CONFIG_FILENAME
    if not path.is_file():
        return session
    try:
        payload = json.loads(path.read_text())
        entries = payload if isinstance(payload, list) else payload["rois"]
    except Exception as error:
        logger.warning(f"Could not load ROI config {path}: {error}")
        return AnalysisSession(directory=str(experiment_directory))

    rois = []
    for entry in entries:
        try:
            rois.append(_roi_from(entry))
        except Exception as error:
            logger.warning(f"Skipping unreadable ROI entry in {path}: {error}")
    session.rois = rois

    if isinstance(payload, dict):
        try:
            session.excluded_images = [
                str(name) for name in payload.get("excluded_images", [])
            ]
        except Exception as error:
            logger.warning(f"Ignoring invalid excluded_images in {path}: {error}")
        try:
            session.plot_stat = payload.get("plot_stat", "mean")
        except Exception as error:
            logger.warning(f"Ignoring invalid plot_stat in {path}: {error}")
        try:
            session.heater_log_dir = str(payload.get("heater_log_dir", ""))
        except Exception as error:
            logger.warning(f"Ignoring invalid heater_log_dir in {path}: {error}")
        try:
            figure = FigureSettings()
            stored = dict(payload.get("figure", {}))
            # Renamed from "standard": a reference is what it is, and
            # a config written before the rename still means it.
            if (
                "subtract_background_ref" not in stored
                and "subtract_standard" in stored
            ):
                stored["subtract_background_ref"] = stored["subtract_standard"]
            figure.trait_set(
                **{name: stored[name] for name in _FIGURE_FIELDS if name in stored}
            )
            session.figure = figure
        except Exception as error:
            logger.warning(f"Ignoring invalid figure settings in {path}: {error}")
        try:
            scale = ScaleCalibration()
            scale.trait_set(
                **{
                    name: payload.get("scale", {})[name]
                    for name in _SCALE_FIELDS
                    if name in payload.get("scale", {})
                }
            )
            session.scale = scale
        except Exception as error:
            logger.warning(f"Ignoring invalid scale settings in {path}: {error}")
        try:
            ring = BackgroundRing()
            ring.trait_set(
                **{
                    name: payload.get("ring", {})[name]
                    for name in _RING_FIELDS
                    if name in payload.get("ring", {})
                }
            )
            session.ring = ring
        except Exception as error:
            logger.warning(f"Ignoring invalid ring settings in {path}: {error}")
        try:
            ball = RollingBall()
            ball.trait_set(
                **{
                    name: payload.get("ball", {})[name]
                    for name in _BALL_FIELDS
                    if name in payload.get("ball", {})
                }
            )
            session.ball = ball
        except Exception as error:
            logger.warning(f"Ignoring invalid rolling-ball settings in {path}: {error}")
        try:
            stored = payload.get("perspective", {})
            perspective = PerspectiveCorrection(enabled=stored.get("enabled", False))

            # JSON hands the points back as lists; the traits hold tuples.
            for name in ("source_quad", "target_quad"):
                points = [tuple(point) for point in stored.get(name, [])]
                perspective.trait_set(**{name: points})

            session.perspective = perspective
        except Exception as error:
            logger.warning(f"Ignoring invalid perspective settings in {path}: {error}")

    return session


def _relative_to(experiment_directory, path):
    """``path`` written against the experiment folder where it sits
    inside it — shorter, and it survives the folder being moved or
    copied, which an absolute path in a cache does not."""
    try:
        return Path(path).relative_to(Path(experiment_directory)).as_posix()
    except ValueError:
        return str(path)


def save_roi_stats(experiment_directory, stats):
    """The computed-stats store, grouped by image and one measurement
    per line (json allows the NaN literal, which Python's parser reads
    back, so this stays lossless).

    Grouped because the flat form repeated every image's path and mtime
    once per ROI per settings combination — on a 12-image experiment
    that was the same 126-character path written 48 times, a fifth of
    the file. One measurement per line rather than pretty-printed
    throughout: the record is the unit worth reading, and a file of one
    record per line can be scanned, grepped and diffed."""
    grouped = {}
    for key, value in stats.items():
        path, mtime, roi_id, kind, geometry, correction = key
        grouped.setdefault((path, mtime), []).append(
            {
                "roi_id": roi_id,
                "kind": kind,
                "geometry": list(geometry),
                "correction": list(correction),
                "stats": value,
            }
        )
    lines = ["{", '  "version": 2,', '  "images": [']
    images = sorted(grouped)
    for index, (path, mtime) in enumerate(images):
        file = _relative_to(experiment_directory, path)
        lines.append("    {")
        lines.append(f'      "file": {json.dumps(file)},')
        lines.append(f'      "mtime": {json.dumps(mtime)},')
        lines.append('      "measurements": [')
        measurements = grouped[(path, mtime)]
        for position, measurement in enumerate(measurements):
            comma = "," if position < len(measurements) - 1 else ""
            lines.append("        " + json.dumps(measurement) + comma)
        lines.append("      ]")
        lines.append("    }" + ("," if index < len(images) - 1 else ""))
    lines.append("  ]")
    lines.append("}")
    path = analysis_directory(experiment_directory) / ROI_STATS_FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stats_key(entry):
    """The cache key a stats entry answers to, migrated the same way
    the ROI it belongs to is — so intensities computed before shapes
    could rotate keep matching after."""
    kind, geometry = normalize(entry["kind"], entry["geometry"])
    # An entry without a ring predates the annulus: its outline stats
    # came from a stroke straddling the boundary, so None here keeps it
    # from ever matching a current key.
    ring = entry.get("ring")
    if ring is not None and len(ring) < 3:
        # Written before the rolling ball existed, which is to say it
        # was computed with no ball — radius 0, exactly what a current
        # key carries when the ball is off. Padding rather than
        # discarding keeps every stored intensity valid.
        ring = list(ring) + [0]
    if ring is not None and len(ring) < 4:
        # Written before the perspective correction existed: measured
        # unwarped, which is what a current key carries when it is off.
        ring = list(ring) + [()]
    if ring is not None:
        # The perspective matrix comes back from JSON as a list.
        ring = list(ring[:3]) + [tuple(ring[3])]
    return (
        entry["path"],
        float(entry["mtime"]),
        entry["roi_id"],
        kind,
        tuple(geometry),
        tuple(ring) if ring is not None else None,
    )


def _flatten_images(experiment_directory, images):
    """The grouped (version 2) form read back as the flat entries
    _stats_key understands, with each file resolved against the
    experiment folder it was written relative to."""
    for image in images:
        # Relative entries are resolved against the folder they were
        # written under; an absolute one is a file that lives outside
        # it and is stored, and used, as it stands.
        stored = Path(image["file"])
        path = stored if stored.is_absolute() else Path(experiment_directory) / stored
        for measurement in image["measurements"]:
            yield {
                "path": str(path),
                "mtime": image["mtime"],
                "roi_id": measurement["roi_id"],
                "kind": measurement["kind"],
                "geometry": measurement["geometry"],
                "ring": measurement["correction"],
                "stats": measurement["stats"],
            }


def load_roi_stats(experiment_directory) -> dict:
    """The persisted stats store, {} when absent/unreadable/unknown
    version. Entries that no longer match anything (moved ROI, changed
    file) are simply never looked up — invalidation stays automatic.

    Reads the flat version-1 form as well, so an experiment measured
    before the file was grouped keeps its numbers."""
    path = Path(experiment_directory) / ANALYSIS_DIR_NAME / ROI_STATS_FILENAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        version = payload["version"]
        if version == 1:
            entries = payload["entries"]
        elif version == 2:
            entries = _flatten_images(experiment_directory, payload["images"])
        else:
            logger.warning(f"Unknown ROI stats version in {path}")
            return {}
        keyed = ((_stats_key(entry), entry["stats"]) for entry in entries)
        # An entry predating the background annulus can never match a
        # current key, and carrying it would break the next save (its
        # ring is None). Drop it here instead.
        return {key: stats for key, stats in keyed if key[5] is not None}
    except Exception as error:
        logger.warning(f"Could not load ROI stats {path}: {error}")
        return {}


#: Per-ROI CSV columns, in order: interior stats, outline stats, then
#: the values derived from the pixel count and the scale.
CSV_STAT_COLUMNS = tuple(STAT_NAMES) + tuple(
    OUTLINE_STATS_PREFIX + name for name in STAT_NAMES
)
CSV_DERIVED_COLUMNS = ("area", "integrated", "bg_integrated", "per_area", "bg_per_area")


def _csv_cell(stats, stat, pixel_area):
    """A derived value, blank where the stats cannot supply it — the
    same empty cell an uncomputed image already writes."""
    value = stat_value(stats, stat, pixel_area)
    return "" if value != value else value


def _normalised_columns(rows, rois, normalize_stat, pixel_area):
    """{roi_id: [cell, ...]} for the normalised column, run through the
    plot's own normaliser so a CSV column and its curve can never
    disagree."""
    series = {
        roi.roi_id: (
            roi.name,
            list(range(len(rows))),
            [
                stat_value(row["stats"].get(roi.roi_id, {}), normalize_stat, pixel_area)
                for row in rows
            ],
        )
        for roi in rois
    }
    return {
        roi_id: ["" if value != value else value for value in values]
        for roi_id, (_name, _elapsed, values) in normalized_series(series).items()
    }


def write_intensity_csv(
    csv_path,
    rows,
    rois,
    pixel_area=1.0,
    area_unit_label="px²",
    normalize_stat=None,
    correction=None,
    outliers=None,
    heater_sensor="",
    filter_column="filter",
):
    """One row per (image, ROI), blank cells where that pair has no
    computed stats. ``rows``: [{"filename", "time_utc", "elapsed_sec",
    "temperature_c", "capture_session", "filter",
    "stats": {roi_id: stats_dict}}, ...] — ``temperature_c`` is the
    heater log's reading at the capture (NaN when uncovered, written
    blank), measured by ``heater_sensor`` (recorded with the other
    settings so the column stays self-describing). ``filter_column``
    heads the image filter's column (e.g. "wavelength").
    ``pixel_area`` scales the derived size-aware columns; it is 1.0
    (px²) for an uncalibrated experiment. ``correction`` is the
    session's (gap, width, ball radius, perspective matrix), recorded on
    every row (the matrix as a 0/1 perspective_corrected flag).

    Long rather than wide: the ROI is a VALUE in a column, not a prefix
    repeated across seventeen column names per ROI. Six ROIs used to
    mean 108 columns and every stat name spelled six times; here the
    width is fixed whatever the ROI count, each frame's ROIs sit
    together as a block, and a reader groups by ``roi`` or filters to
    one without counting columns. It is also what pandas, R and every
    plotting library want handed to them."""
    header = (
        [
            "index",
            "time_utc",
            "elapsed_sec",
            "temperature_c",
            "filename",
            "capture_session",
            filter_column,
            "roi",
            "is_background_ref",
        ]
        + list(CSV_STAT_COLUMNS)
        + [f"area_{area_unit_label}"]
        + list(CSV_DERIVED_COLUMNS[1:])
    )
    if normalize_stat is not None:
        header += [f"{normalize_stat}_norm_pct"]
    # What the numbers were measured with. Constant down the file, but
    # it is the difference between two exports that otherwise look
    # identical, and it keeps a row self-describing once files are
    # concatenated.
    header += [
        "outlier",
        "ring_gap_px",
        "ring_width_px",
        "ball_radius_px",
        "perspective_corrected",
        "heater_sensor",
    ]
    gap, width, ball, perspective = (
        correction if correction is not None else (0, 0, 0, ())
    )
    settings = [gap, width, ball, int(bool(perspective)), heater_sensor]
    normalised = (
        {}
        if normalize_stat is None
        else _normalised_columns(rows, rois, normalize_stat, pixel_area)
    )
    # utf-8, not the platform default: the area header carries µ and ².
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index, row in enumerate(rows):
            temperature = row.get("temperature_c", math.nan)
            shared = [
                index,
                row["time_utc"],
                row["elapsed_sec"],
                "" if temperature != temperature else temperature,
                row["filename"],
                row["capture_session"],
                row["filter"],
            ]
            for roi in rois:
                stats = row["stats"].get(roi.roi_id, {})
                record = shared + [roi.name, int(roi.is_background_ref)]
                record += [stats.get(stat, "") for stat in CSV_STAT_COLUMNS]
                record += [
                    _csv_cell(stats, stat, pixel_area) for stat in CSV_DERIVED_COLUMNS
                ]
                if normalize_stat is not None:
                    record += [normalised[roi.roi_id][index]]
                flags = (outliers or {}).get(roi.roi_id) or []
                record += [int(bool(flags[index])) if index < len(flags) else 0]
                writer.writerow(record + settings)


def load_fit_equations(experiment_directory) -> dict:
    """The saved fitted parameters, {} when absent or unreadable:
    {equation: {roi name: {parameter: value}}}."""
    path = Path(experiment_directory) / ANALYSIS_DIR_NAME / FIT_EQUATIONS_FILENAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as error:
        logger.warning(f"Could not load fit equations {path}: {error}")
        return {}


def save_fit_equations(experiment_directory, equation, fits):
    """Record what ``equation`` fitted to, as
    {ROI: {"params": {...}, "r_squared": ..., "fitted_range_sec": ...,
    "trimmed": ...}}.

    The parameters sit under their own key rather than at the top of
    the ROI's dict: an equation is free to name a parameter anything,
    ``r_squared`` included, and a fitted value must never be mistaken
    for the quality of the fit that produced it.

    Keyed by the equation in symbolic form, so the file accumulates one
    entry per model tried on this experiment rather than only the last
    — fitting a sigmoid and then a custom decay leaves both, which is
    what makes the file worth keeping.

    The ROI sits between the equation and its parameters because every
    ROI is fitted separately: one equation, one parameter set each."""
    if not equation or not fits:
        return
    payload = load_fit_equations(experiment_directory)
    # The whole entry is replaced, not merged per ROI: it is the fit of
    # the ROIs that exist now, and a deleted one should not linger.
    payload[equation] = fits
    path = analysis_directory(experiment_directory) / FIT_EQUATIONS_FILENAME
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
