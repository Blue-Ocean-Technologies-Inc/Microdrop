# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Show the ROI plot pane alone over synthetic experiments, for
iterating on plotting several experiments without launching the app.

Writes three experiments under a folder (a fresh temporary one unless
given): "Condition A" — live at start — "Condition B", an hour later
with a later rise, and "Condition C", earlier and steeper. B is plotted
at start: its saved analysis restyles one ROI (STORED_STYLE) and
excludes its first images (STORED_EXCLUDED), drawn as excluded points.
Import C through the "Import experiment…" button above the tree, untick
a section's "Align to run start" to see its run land on A's clock, pick
a fit on the Fit tab to see every experiment's ROIs fitted alike, and
click B's section to make it live — the demo stands in for the image
viewer (show_experiment), saving A and loading B as a switch does.

    pixi run python -m image_viewer.demos.experiment_comparison_demo [folder]
"""

# Standard library imports.
import math
import sys
import tempfile
import time
from pathlib import Path

# Third-party imports.
import numpy as np

# Enthought library imports.
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME

# Local imports.
from ..analysis.consts import DEFAULT_ROI_COLORS
from ..analysis.imported_experiments_model import imported_experiments_model
from ..analysis.plot_pane import RoiPlotDockPane
from ..analysis.roi_model import AnalysisSession, Roi, RoiStyle, roi_analysis_model
from ..analysis.roi_store import (
    load_roi_stats,
    load_session,
    save_roi_stats,
    save_session,
)
from ..consts import CAPTURE_TIMESTAMP_FORMAT

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Captures per experiment, and the seconds between them.
FRAMES = 40
FRAME_INTERVAL_S = 15.0

#: The analysed experiment's first capture (UTC epoch s).
FIRST_CAPTURE_EPOCH = 1_784_538_000.0

#: Per experiment: (folder name, hours after the first, ROI names, rise
#: onset in s, rise width in s, plateau gain).
EXPERIMENTS = (
    ("Condition A", 0, ("Drop 1", "Drop 2", "Drop 3"), 200.0, 40.0, 1.0),
    ("Condition B", 1, ("Drop 1", "Drop 2", "Drop 3"), 320.0, 60.0, 0.8),
    ("Condition C", 2, ("Sample L", "Sample M", "Sample R"), 150.0, 25.0, 1.2),
)

#: Each ROI's baseline and rise (intensity units), by position.
ROI_LEVELS = ((400.0, 1800.0), (600.0, 1200.0), (300.0, 2400.0))

#: Condition B's first ROI's saved style: square markers, a dotted
#: line and half alpha.
STORED_STYLE = {"marker": "s", "line_style": "dotted", "alpha": 50}

#: How many of Condition B's first images its saved analysis excludes.
STORED_EXCLUDED = 3


def _write_experiment(root, name, hours, roi_names, onset, width, gain, rng):
    """One synthetic experiment: empty timestamped captures and a saved
    session whose ROIs measure a noisy sigmoid rise on every one."""
    directory = root / name
    captures = directory / CAPTURES_DIR_NAME
    captures.mkdir(parents=True, exist_ok=True)
    rois = [
        Roi(
            name=roi_name,
            kind="ellipse",
            geometry=[100.0 + 80.0 * index, 100.0, 20.0, 20.0, 0.0],
            style=RoiStyle(color=DEFAULT_ROI_COLORS[index], marker="o"),
        )
        for index, roi_name in enumerate(roi_names)
    ]
    session = AnalysisSession(directory=str(directory), rois=rois)
    start = FIRST_CAPTURE_EPOCH + hours * 3600.0

    for frame in range(FRAMES):
        elapsed = frame * FRAME_INTERVAL_S
        stamp = time.strftime(CAPTURE_TIMESTAMP_FORMAT, time.gmtime(start + elapsed))
        path = captures / f"capture_{stamp}_raw.png"
        path.write_bytes(b"")
        rise = 1.0 / (1.0 + math.exp(-(elapsed - onset) / width))

        for roi, (base, amplitude) in zip(rois, ROI_LEVELS):
            mean = base + gain * amplitude * rise + rng.normal(0.0, 25.0)
            session.stats[session.cache_key(str(path), roi)] = {
                "mean": mean,
                "outline_mean": base * 0.5,
                "count": 1250,
            }

    save_session(directory, session)
    save_roi_stats(directory, session.stats)

    return directory


def _restyle_saved(directory):
    """Give the experiment in ``directory`` STORED_STYLE on its first ROI
    and its first STORED_EXCLUDED images excluded, in its saved
    analysis."""
    session = load_session(directory)
    captures = sorted((directory / CAPTURES_DIR_NAME).iterdir())
    session.rois[0].style.trait_set(**STORED_STYLE)
    session.excluded_images = [path.name for path in captures[:STORED_EXCLUDED]]
    save_session(directory, session)


def _show(directory):
    """Make the experiment in ``directory`` live, as the viewer does:
    its paths before its session."""
    session = load_session(directory)
    session.stats = load_roi_stats(directory)
    roi_analysis_model.filtered_paths = [
        str(path) for path in sorted((directory / CAPTURES_DIR_NAME).iterdir())
    ]
    roi_analysis_model.session = session


def show_experiment(event):
    """Stand in for the image viewer a section click asks: save the live
    experiment, then show the clicked one."""
    live = roi_analysis_model.session
    save_session(live.directory, live)
    save_roi_stats(live.directory, live.stats)
    _show(Path(event.new))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
    rng = np.random.default_rng(7)
    directories = [
        _write_experiment(root, *experiment, rng) for experiment in EXPERIMENTS
    ]
    primary, stored = directories[0], directories[1]
    _restyle_saved(stored)
    logger.info(f"Synthetic experiments in {root}")

    app = QApplication.instance() or QApplication(sys.argv)
    _show(primary)
    imported_experiments_model.add_experiment(stored)
    imported_experiments_model.observe(show_experiment, "open_experiment_request")

    pane = RoiPlotDockPane()
    widget = pane.create_contents(None)
    widget.setWindowTitle("Plotted experiments")
    widget.resize(960, 1000)
    widget.show()
    roi_analysis_model.plot_visible = True

    app.exec()


if __name__ == "__main__":
    main()
