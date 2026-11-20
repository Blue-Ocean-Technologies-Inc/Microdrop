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

# Enthought library imports.
from pyface.qt import QtWidgets
from traits.api import Instance, Int
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor


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

        # Imported here: only a shown figure should load matplotlib's Qt
        # backend (the frontends that never plot skip it entirely).
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

        self.canvas = FigureCanvasQTAgg(self.value)
        self.canvas.setMinimumHeight(self.factory.min_height)
        self.control.layout().addWidget(self.canvas)
        self.canvas.draw_idle()

    def dispose(self):
        self._remove_canvas()
        super().dispose()

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
