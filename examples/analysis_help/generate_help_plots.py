# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Regenerate the Image Analysis Tutorial's example plot figures.

Renders one figure per plot-pane View the page shows (Over time, 2nd
derivative, Fastest change) through the real ``RoiPlotCanvas`` over a
synthetic ROI series, so the figures are what the app itself draws. For
each view mode it writes ``view_<mode>.svg``, post-processed for the page
(text kept as text, styles gathered into one scoped sheet per figure), which
``image_viewer/resources/analysis_help.src.html`` inlines. Rebuild the page
afterwards (``examples/tutorials/build_tutorial.py``).

Output goes to ``image_viewer/resources/analysis_help_media/`` (next to the
tutorial source) unless an output folder is given. From ``src``::

    pixi run python -m examples.analysis_help.generate_help_plots [out_dir]

Set ``QT_QPA_PLATFORM=offscreen`` to run without a display.
"""

# Standard library imports.
import io
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
from image_viewer.analysis.consts import DEFAULT_ROI_COLORS
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

DEFAULT_OUTPUT_DIR = ANALYSIS_HELP_HTML_PATH.parent / "analysis_help_media"
#: The view modes the page shows, each with a short id and class prefix so
#: the figures can share the page.
FIGURE_PREFIXES = {"intensity": "i", "second_derivative": "sd", "fastest_change": "fc"}
#: matplotlib's text font, kept as one rule per figure instead of on every
#: label.
MPL_FONT_FAMILY = re.compile(r"font-family: [^;\"]*(; )?")
#: Splits markup into tags and the text between them.
SVG_TAG_TOKEN = re.compile(r"(<[^>]+>)")
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
    """Make a matplotlib SVG embeddable in the offline tutorial page.

    Drops the XML prolog, metadata and namespace URLs (HTML parses inline
    SVG without them), rounds coordinates to 0.1 pt and collapses the
    layout whitespace, then compacts it (see ``compact_svg``).
    """
    svg = svg[svg.index("<svg") :]
    svg = re.sub(r"\s*<metadata>.*?</metadata>", "", svg, flags=re.S)
    svg = re.sub(r'\s+xmlns(:\w+)?="[^"]*"', "", svg)
    svg = re.sub(r'\s+(width|height)="[\d.]+pt"', "", svg, count=2)

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

    svg = re.sub(r"\s*\n\s*", " ", svg)
    svg = svg.replace("> <", "><")

    return compact_svg(svg.strip(), prefix) + "\n"


def compact_svg(svg, prefix):
    """Shrink an inlined matplotlib figure without changing how it draws.

    Every ``style`` attribute becomes a class in one sheet scoped to the
    figure (root class ``prefix``), which also carries matplotlib's own
    defaults and its text font; only referenced ids are kept, renamed
    ``<prefix><n>``; identity rotations and bare ``<g>`` wrappers go. The
    page's tutorial kit styles ``svg text``, so the sheet sets the text
    colour and font the figure was drawn with.
    """
    svg = re.sub(r"<defs><style[^>]*>.*?</style></defs>", "", svg, flags=re.S)
    svg = re.sub(r' transform="rotate\(-0 [\d.]+ [\d.]+\)"', "", svg)
    font = MPL_FONT_FAMILY.search(svg)
    svg = MPL_FONT_FAMILY.sub("", svg)
    svg = svg.replace("xlink:href=", "href=")

    referenced = re.findall(r'(?:url\(#|href="#)([^)"]+)', svg)
    ids = {old: f"{prefix}{n}" for n, old in enumerate(dict.fromkeys(referenced))}
    svg = re.sub(
        r' id="([^"]+)"',
        lambda m: f' id="{ids[m[1]]}"' if m[1] in ids else "",
        svg,
    )
    svg = re.sub(r'(url\(#|href="#)([^)"]+)', lambda m: m[1] + ids[m[2]], svg)

    classes = {}

    def classed(match):
        css = match[1].strip().rstrip(";").replace(": ", ":").replace("; ", ";")

        if not css:
            return ""

        return f' class="{classes.setdefault(css, f"{prefix}s{len(classes)}")}"'

    svg = re.sub(r' style="([^"]*)"', classed, svg)

    kept = []
    bare = []

    for token in SVG_TAG_TOKEN.split(svg):
        if token.startswith("<g") and token[2] in " >":
            bare.append(token == "<g>")

            if token == "<g>":
                continue

        elif token == "</g>" and bare.pop():
            continue

        kept.append(token)

    rules = [
        f".{prefix} *{{stroke-linejoin:round;stroke-linecap:butt}}",
        f".{prefix} text{{fill:#000;{font[0].rstrip('; ').replace(': ', ':')}}}",
        *(f".{name}{{{css}}}" for css, name in classes.items()),
    ]
    svg = "".join(kept).replace("<svg ", f'<svg class="{prefix}" ', 1)
    root_end = svg.index(">") + 1

    return f"{svg[:root_end]}<style>{''.join(rules)}</style>{svg[root_end:]}"


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

        for mode in FIGURE_PREFIXES:
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
            drawn = io.StringIO()
            canvas.figure.savefig(drawn, format="svg", metadata={"Date": None})

            target = out / f"view_{mode}.svg"
            target.write_text(
                inline_svg(drawn.getvalue(), FIGURE_PREFIXES[mode]),
                encoding="utf-8",
                newline="\n",
            )
            logger.info(f"{target}: {target.stat().st_size} bytes")

        canvas.detach()


if __name__ == "__main__":
    main()
