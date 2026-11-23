# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""theme_figure repaints a figure's chrome in palette colours and leaves the
data colours alone."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.matplotlib_editors import theme_figure

pytest.importorskip("matplotlib")

BASE, TEXT, MID = "#1e1e1e", "#ffffff", "#575757"


def _figure():
    from matplotlib.figure import Figure

    figure = Figure()
    figure.suptitle("Voltage")
    axes = figure.add_subplot()
    axes.plot([0, 1], [0, 1], "k--", label="identity")
    axes.plot([0, 1], [1, 0], color="tab:blue", label="data")
    axes.set_title("sweep")
    axes.grid(True)
    axes.legend()

    return figure, axes


def test_theme_figure_paints_the_chrome_and_keeps_the_data_colours():
    from matplotlib.colors import to_hex

    figure, axes = _figure()
    reference, data = axes.get_lines()

    theme_figure(figure, BASE, TEXT, MID)

    assert to_hex(figure.patch.get_facecolor()) == BASE
    assert to_hex(axes.get_facecolor()) == BASE
    assert to_hex(figure.texts[0].get_color()) == TEXT
    assert to_hex(axes.title.get_color()) == TEXT
    assert to_hex(axes.spines["left"].get_edgecolor()) == TEXT
    assert to_hex(axes.get_xgridlines()[0].get_color()) == MID
    assert to_hex(axes.get_legend().get_frame().get_edgecolor()) == MID
    assert to_hex(reference.get_color()) == TEXT
    assert to_hex(data.get_color()) == to_hex("tab:blue")
