# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI editor showing a matplotlib ``Figure`` trait on a Qt canvas.
Generic: the model draws a pyplot-free Figure, this editor only shows it.
matplotlib is imported only when a canvas is made, so importing a view that
uses this editor does not load it."""

# Standard library imports.
import functools

# Enthought library imports.
from pyface.qt import QtGui, QtWidgets
from traits.api import Bool, Instance, Int
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

# Microdrop style imports.
from microdrop_style.helpers import is_dark_mode

#: RGB of the black reference lines ("k--" identity, baselines) that would
#: vanish on a dark background.
BLACK_RGB = (0.0, 0.0, 0.0)


@functools.cache
def scroll_through_canvas_class():
    """The canvas class: matplotlib's Qt canvas, but leaving the mouse wheel
    to the widgets around it. The shown figures take no wheel input, and a
    canvas that kept it would stop a scrollable pane from scrolling while
    the pointer is over its plot."""
    # Imported here: only a shown figure should load matplotlib's Qt
    # backend (the frontends that never plot skip it entirely).
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    class ScrollThroughFigureCanvas(FigureCanvasQTAgg):
        def wheelEvent(self, event):
            event.ignore()

    return ScrollThroughFigureCanvas


def theme_figure(figure, base, text, mid):
    """Paint an on-screen ``figure`` in UI palette colours: ``base`` for the
    backgrounds, ``text`` for axes, ticks, labels, titles and black
    reference lines, ``mid`` for the grid and the legend frame. Data colours
    stay. Ported from the vendor UI's ``self_test_plots.theme_figure``, which
    reads the colours from Qt itself; exports never call it."""
    # Imported here: only a shown figure should load matplotlib.
    from matplotlib.colors import to_rgb

    figure.patch.set_facecolor(base)

    for figure_text in figure.texts:
        figure_text.set_color(text)

    for axes in figure.axes:
        axes.set_facecolor(base)
        axes.tick_params(colors=text, which="both")
        axes.xaxis.label.set_color(text)
        axes.yaxis.label.set_color(text)
        axes.title.set_color(text)

        for spine in axes.spines.values():
            spine.set_edgecolor(text)

        for line in axes.get_xgridlines() + axes.get_ygridlines():
            line.set_color(mid)

        for line in axes.get_lines():
            try:
                if to_rgb(line.get_color()) == BLACK_RGB:
                    line.set_color(text)

            except ValueError:
                # A colour matplotlib cannot read as RGB is no black line.
                pass

        legend = axes.get_legend()

        if legend is not None:
            legend.get_frame().set_facecolor(base)
            legend.get_frame().set_edgecolor(mid)

            for legend_text in legend.get_texts():
                legend_text.set_color(text)


class _MatplotlibFigureEditor(QtEditor):
    """The Qt half: a container holding one canvas, swapped for a new one
    whenever the trait is assigned a different Figure (a Figure draws on
    one canvas at a time)."""

    #: The canvas of the Figure shown; None while the trait is None.
    canvas = Instance("matplotlib.backends.backend_qtagg.FigureCanvasQTAgg")

    def init(self, parent):
        self.control = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.control)
        layout.setContentsMargins(0, 0, 0, 0)

        self.update_editor()

    def update_editor(self):
        """Show the trait's Figure, redrawing it when it is the same one."""

        if self.canvas is not None and self.canvas.figure is self.value:
            self.canvas.draw_idle()

            return

        self._remove_canvas()

        if self.value is None:
            return

        if self.factory.follow_dark_theme and is_dark_mode():
            self._theme_from_palette()

        self.canvas = scroll_through_canvas_class()(self.value)
        self.canvas.setMinimumHeight(self.factory.min_height)
        self.control.layout().addWidget(self.canvas)
        self.canvas.draw_idle()

    def dispose(self):
        self._remove_canvas()
        super().dispose()

    def _theme_from_palette(self):
        palette = QtWidgets.QApplication.palette()
        roles = QtGui.QPalette.ColorRole
        base, text, mid = (
            palette.color(role).name() for role in (roles.Base, roles.Text, roles.Mid)
        )

        theme_figure(self.value, base, text, mid)

    def _remove_canvas(self):
        if self.canvas is None:
            return

        self.canvas.setParent(None)
        self.canvas.deleteLater()
        self.canvas = None


class MatplotlibFigureEditor(BasicEditorFactory):
    """Show an ``Instance(Figure)`` trait; reassign the trait to redraw."""

    klass = _MatplotlibFigureEditor

    #: Minimum canvas height (px): a squeezed figure is unreadable.
    min_height = Int(300)

    #: In dark mode, repaint each shown Figure in the app palette's colours
    #: (``theme_figure``). It recolours the trait's Figure itself, so use it
    #: only for Figures drawn for the screen.
    follow_dark_theme = Bool(False)
