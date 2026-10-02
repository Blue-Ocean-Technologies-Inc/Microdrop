# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Regenerate the analysis help guide's example plot figures.

Renders one figure per plot-pane View (Intensity, 2nd derivative, Fastest
change) through the real ``RoiPlotCanvas`` over a synthetic ROI series, so
the figures are what the app itself draws. For each view mode it writes
``view_<mode>.svg`` (text kept as text), a ``view_<mode>.png`` preview, and
``view_<mode>.inline.svg`` — the post-processed copy to paste into
``image_viewer/resources/analysis_help.html``.

Output goes to ``image_viewer/resources/analysis_help/`` (next to the help
HTML) unless an output folder is given. From ``src``::

    pixi run python -m examples.analysis_help.generate_help_plots [out_dir]

Set ``QT_QPA_PLATFORM=offscreen`` to run without a display.
"""

# Standard library imports.
import re
import sys
import tempfile
import time
from pathlib import Path

# Third-party imports.
import matplotlib
import numpy as np

# Enthought library imports.
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from image_viewer.analysis.consts import DEFAULT_ROI_COLORS, VIEW_MODES
from image_viewer.analysis.plot_pane import RoiPlotCanvas
from image_viewer.analysis.roi_model import (
    AnalysisSession,
    FigureSettings,
    Roi,
    RoiAnalysisModel,
    RoiStyle,
)
from image_viewer.consts import ANALYSIS_HELP_HTML_PATH

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

DEFAULT_OUTPUT_DIR = ANALYSIS_HELP_HTML_PATH.parent / "analysis_help"
N_IMAGES = 30
INTERVAL_S = 10
#: (name, midpoint s, rise steepness s, baseline, plateau)
ROI_CURVES = (
    ("Droplet A", 110.0, 18.0, 210.0, 820.0),
    ("Droplet B", 150.0, 22.0, 190.0, 700.0),
    ("Droplet C", 190.0, 16.0, 230.0, 900.0),
)
#: (ROI index, image index, value) — a camera glitch for the outlier test.
OUTLIER = (1, 8, 760.0)


def make_images(folder):
    """Create empty image files whose names carry the capture timestamps."""
    start = time.mktime((2026, 7, 20, 10, 0, 0, 0, 0, -1))
    paths = []

    for index in range(N_IMAGES):
        stamp = time.strftime(
            "%Y_%m_%d-%H_%M_%S", time.localtime(start + index * INTERVAL_S)
        )
        path = folder / f"img{index:02d}_{stamp}_raw.png"
        path.write_bytes(b"")
        paths.append(str(path))

    return paths


def synthetic_series():
    """Return (elapsed seconds, [values per ROI]) — noisy sigmoid rises.

    One injected glitch exercises outlier removal. The help page's
    walkthrough panel uses the same series, so its toy curve and these
    figures agree.
    """
    rng = np.random.default_rng(7)
    t = np.arange(N_IMAGES) * INTERVAL_S
    curves = []

    for index, (_, mid, k, low, high) in enumerate(ROI_CURVES):
        values = low + (high - low) / (1.0 + np.exp(-(t - mid) / k))
        values = values + rng.normal(0.0, 8.0, size=t.size)

        if index == OUTLIER[0]:
            values[OUTLIER[1]] = OUTLIER[2]

        curves.append(values)

    return t, curves


def make_session(paths):
    """Build an AnalysisSession whose stats cache holds the synthetic series."""
    rois = [
        Roi(
            name=name,
            kind="ellipse",
            geometry=[50.0 + 60 * index, 50.0, 20.0, 20.0, 0.0],
            style=RoiStyle(color=DEFAULT_ROI_COLORS[index]),
        )
        for index, (name, *_) in enumerate(ROI_CURVES)
    ]

    session = AnalysisSession(rois=rois, figure=FigureSettings())
    _, curves = synthetic_series()

    for roi, values in zip(rois, curves):
        for path, value in zip(paths, values):
            session.stats[session.cache_key(path, roi)] = {
                "mean": float(value),
                "outline_mean": 150.0,
                "count": 1250,
            }

    return session


def inline_svg(svg, prefix):
    """Make a matplotlib SVG embeddable in the offline help page.

    Drops the XML prolog, metadata and namespace URLs (HTML parses inline
    SVG without them), rounds coordinates to 0.1 pt, and prefixes ids so
    several figures can share one page.
    """
    svg = svg[svg.index("<svg") :]
    svg = re.sub(r"\s*<metadata>.*?</metadata>", "", svg, flags=re.S)
    svg = re.sub(r'\s+xmlns(:\w+)?="[^"]*"', "", svg)
    svg = re.sub(r'\s+(width|height)="[\d.]+pt"', "", svg, count=2)
    svg = svg.replace("<svg ", '<svg class="mpl" role="img" ', 1)

    # Round inside tags only: text content (tick labels, coordinates)
    # must keep the app's own formatting.
    svg = re.sub(
        r"<[^>]+>",
        lambda tag: re.sub(
            r"-?\d+\.\d+",
            lambda m: f"{float(m.group()):.1f}".rstrip("0").rstrip("."),
            tag.group(),
        ),
        svg,
    )

    svg = re.sub(r'id="([^"]+)"', rf'id="{prefix}-\1"', svg)
    svg = re.sub(r"url\(#([^)]+)\)", rf"url(#{prefix}-\1)", svg)
    svg = re.sub(r'href="#([^"]+)"', rf'href="#{prefix}-\1"', svg)
    svg = re.sub(r"\s*\n\s*", " ", svg)
    svg = svg.replace("> <", "><")

    return svg.strip() + "\n"


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    matplotlib.rcParams["svg.fonttype"] = "none"
    matplotlib.rcParams["svg.hashsalt"] = "microdrop-help"

    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as folder:
        paths = make_images(Path(folder))
        model = RoiAnalysisModel(session=make_session(paths), filtered_paths=paths)
        figure = model.session.figure
        figure.fit_method = "sigmoid"
        figure.remove_outliers = True

        canvas = RoiPlotCanvas(model)
        canvas.resize(640, 400)
        canvas.show()
        app.processEvents()

        for mode in VIEW_MODES:
            figure.view_mode = mode

            # The d² markers belong to the d² view; on the intensity
            # chart they would crowd the fitted curves.
            figure.show_second_derivative_max = mode == "second_derivative"
            figure.show_second_derivative_min = mode == "second_derivative"
            canvas._refresh()

            if mode == "fastest_change":
                # fixme: #792 — _refresh's set_xscale() after the bars resets
                # the FixedLocator, so the pane shows 0.0..2.5 instead of the
                # ROI names; put the names back until that fix lands.
                names = [name for name, *_ in ROI_CURVES]
                canvas.figure.axes[0].set_xticks(range(len(names)), names)

            canvas.figure.tight_layout()
            target = out / f"view_{mode}.svg"
            canvas.figure.savefig(target, format="svg", metadata={"Date": None})
            canvas.figure.savefig(out / f"view_{mode}.png", dpi=80)

            inline = out / f"view_{mode}.inline.svg"
            inline.write_text(
                inline_svg(target.read_text(encoding="utf-8"), mode),
                encoding="utf-8",
            )
            logger.info(
                f"{target}: {target.stat().st_size} bytes, "
                f"inline {inline.stat().st_size} bytes"
            )

        canvas.detach()


if __name__ == "__main__":
    main()
