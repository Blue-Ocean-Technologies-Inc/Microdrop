# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Run the shape-moments prototype.

From ``microdrop-py/src`` (with ``--manifest-path ../pyproject.toml``)::

    pixi run python -m examples.shape_moments.run [out_dir]

Generates the synthetic droplet series (``synthetic.py``) into
``out_dir/frames``, reads every frame back from disk, measures every
droplet in its ROI with ``descriptors.describe_droplet``, and writes
``descriptors.csv`` plus three figures: each descriptor over time,
each descriptor's distribution per droplet, and a montage of frames
with the detected contours drawn. Headless (matplotlib Agg).
"""

# Standard library imports.
import csv
import sys
from pathlib import Path

# Third-party imports.
import cv2
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Local imports.
from .descriptors import (  # noqa: E402
    DEVIATION_DESCRIPTORS,
    HU_KEYS,
    SCALAR_DESCRIPTORS,
    add_shape_deviation,
    describe_droplet,
)
from .synthetic import generate_series, roi_mask  # noqa: E402

# Logger import.
from logger.logger_service import get_logger  # noqa: E402

logger = get_logger(__name__)

DEFAULT_OUT_DIR = Path(__file__).parent / "output"

#: Descriptors drawn in the over-time and distribution figures.
PLOTTED_DESCRIPTORS = (
    "area",
    "axis_ratio",
    "eccentricity",
    "orientation_deg",
    "circularity",
    "solidity",
    "extent",
    "shape_deviation",
    "hu_log_deviation",
)

#: Frames shown in the contour montage, as fractions through the series.
MONTAGE_PROGRESS = (0.0, 0.33, 0.67, 1.0)

#: One colour per droplet, in ROI order (matplotlib tab10).
DROPLET_COLORS = plt.get_cmap("tab10").colors

CSV_COLUMNS = (
    ("frame", "droplet") + SCALAR_DESCRIPTORS + DEVIATION_DESCRIPTORS + HU_KEYS
)


def measure_series(paths, rois):
    """{droplet: [descriptor dict per frame]} for the frames at ``paths``."""
    frames = [cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) for path in paths]
    results = {}

    for name, roi in rois.items():
        mask = roi_mask(frames[0].shape, roi)
        results[name] = add_shape_deviation(
            [describe_droplet(frame, mask) for frame in frames]
        )

    return frames, results


def write_csv(results, csv_path):
    """One row per (frame, droplet) with every scalar descriptor."""
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)

        for name, series in results.items():
            for index, descriptors in enumerate(series):
                writer.writerow(
                    [index, name] + [descriptors[key] for key in CSV_COLUMNS[2:]]
                )


def _panel_grid(count):
    """A figure with ``count`` axes on a three-column grid."""
    rows = -(-count // 3)
    figure, axes = plt.subplots(rows, 3, figsize=(15, 4 * rows), squeeze=False)

    for unused in axes.flat[count:]:
        unused.set_visible(False)

    return figure, axes.flat


def plot_over_time(results, figure_path):
    """One panel per descriptor, one line per droplet, against frame."""
    figure, axes = _panel_grid(len(PLOTTED_DESCRIPTORS))

    for axis, key in zip(axes, PLOTTED_DESCRIPTORS):
        for color, (name, series) in zip(DROPLET_COLORS, results.items()):
            axis.plot(
                [descriptors[key] for descriptors in series],
                color=color,
                label=name,
                linewidth=1.5,
            )

        axis.set_title(key)
        axis.set_xlabel("frame")
        axis.grid(alpha=0.3)

    axes[0].legend(fontsize="small")
    figure.suptitle("Shape descriptors over time")
    figure.tight_layout()
    figure.savefig(figure_path, dpi=110)
    plt.close(figure)


def plot_distributions(results, figure_path):
    """One panel per descriptor, one violin per droplet."""
    figure, axes = _panel_grid(len(PLOTTED_DESCRIPTORS))
    names = list(results)
    positions = np.arange(1, len(names) + 1)

    for axis, key in zip(axes, PLOTTED_DESCRIPTORS):
        for position, color, name in zip(positions, DROPLET_COLORS, names):
            values = np.array([descriptors[key] for descriptors in results[name]])
            values = values[np.isfinite(values)]

            # A constant series has no density for violinplot's KDE to
            # estimate; a marker shows the single value instead.
            if values.size < 2 or np.ptp(values) == 0:
                axis.plot([position], values[:1], "_", color=color, markersize=20)
                continue

            parts = axis.violinplot(values, [position], showmedians=True)

            for body in parts["bodies"]:
                body.set_facecolor(color)
                body.set_alpha(0.6)

        axis.set_title(key)
        axis.set_xticks(positions, [name.split("_")[0] for name in names])
        axis.grid(alpha=0.3, axis="y")

    figure.suptitle("Descriptor distribution across the series, per droplet")
    figure.tight_layout()
    figure.savefig(figure_path, dpi=110)
    plt.close(figure)


def plot_montage(frames, results, rois, figure_path):
    """A few frames with each ROI (grey) and detected contour drawn."""
    last = len(frames) - 1
    indices = sorted({round(progress * last) for progress in MONTAGE_PROGRESS})
    figure, axes = plt.subplots(1, len(indices), figsize=(4.5 * len(indices), 4.8))

    for axis, index in zip(np.atleast_1d(axes), indices):
        canvas = cv2.cvtColor(frames[index], cv2.COLOR_GRAY2RGB)

        for color, (name, series) in zip(DROPLET_COLORS, results.items()):
            roi = rois[name]
            cv2.circle(canvas, tuple(roi["centre"]), roi["radius"], (110, 110, 110), 1)
            contour = series[index]["contour"]

            if contour is not None:
                rgb = tuple(round(channel * 255) for channel in color)
                cv2.drawContours(canvas, [contour], -1, rgb, 1)

        axis.imshow(canvas)
        axis.set_title(f"frame {index}")
        axis.axis("off")

    figure.suptitle("Detected droplet contours (ROI in grey)")
    figure.tight_layout()
    figure.savefig(figure_path, dpi=110)
    plt.close(figure)


def main(out_dir=DEFAULT_OUT_DIR):
    """Generate, measure, and plot; return the written output paths."""
    out_dir = Path(out_dir)
    paths, series = generate_series(out_dir / "frames")
    frames, results = measure_series(paths, series["rois"])

    outputs = {
        "csv": out_dir / "descriptors.csv",
        "over_time": out_dir / "descriptors_over_time.png",
        "distribution": out_dir / "descriptors_distribution.png",
        "montage": out_dir / "contour_montage.png",
    }
    write_csv(results, outputs["csv"])
    plot_over_time(results, outputs["over_time"])
    plot_distributions(results, outputs["distribution"])
    plot_montage(frames, results, series["rois"], outputs["montage"])

    for label, path in outputs.items():
        logger.info(f"Wrote {label}: {path}")

    return outputs


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_DIR)
