# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The live histogram plot: a QPainter widget, and the TraitsUI editor that
hosts it in the pane's View.

Repainting at up to 20 Hz is why this is raw Qt: a plotting library is too
slow here. The plot follows the application palette, so it reads in both the
light and the dark theme.
"""

# Third-party imports.
import numpy as np

# Enthought library imports.
from pyface.qt.QtCore import QPointF, QRectF, QSize, Qt
from pyface.qt.QtGui import QColor, QPainter, QPalette, QPen, QPolygonF
from pyface.qt.QtWidgets import QSizePolicy, QWidget
from traits.api import observe
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR, INFO_COLOR

# Local imports.
from ...consts import (
    LIVE_HISTOGRAM_BINS,
    LIVE_HISTOGRAM_CHANNEL_COLORS,
    LIVE_HISTOGRAM_CLIP_CUE_MIN_WIDTH_PX,
    LIVE_HISTOGRAM_CLIP_WARN_PCT,
    LIVE_HISTOGRAM_PLOT_MARGIN_PX,
    LIVE_HISTOGRAM_PLOT_MIN_SIZE_PX,
)

#: Fill opacity of the luma histogram, and of each overlaid channel.
LUMA_FILL_ALPHA = 200
CHANNEL_FILL_ALPHA = 140

#: Opacity of the clipping cues and of the 25/50/75 % grid.
CLIP_CUE_ALPHA = 170
GRID_ALPHA = 45

#: Opacity of the "No camera feed" placeholder text.
PLACEHOLDER_ALPHA = 150

#: Grid lines, as fractions of the plot's width and height.
GRID_FRACTIONS = (0.25, 0.5, 0.75)


def text_color(palette, alpha):
    """The palette's text colour at ``alpha``: neutral and legible on its Base
    in either theme."""

    color = QColor(palette.color(QPalette.ColorRole.Text))
    color.setAlpha(alpha)

    return color


class LiveHistogramWidget(QWidget):
    """Paint the model's histogram, with clipping cues at either end."""

    def __init__(self, model, parent=None):
        super().__init__(parent)

        self.model = model

        self.setMinimumSize(*LIVE_HISTOGRAM_PLOT_MIN_SIZE_PX)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        width, height = LIVE_HISTOGRAM_PLOT_MIN_SIZE_PX

        return QSize(width * 3 // 2, height * 3 // 2)

    def paintEvent(self, event):
        palette = self.palette()
        margin = LIVE_HISTOGRAM_PLOT_MARGIN_PX
        plot = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), palette.color(QPalette.ColorRole.Base))

        self._paint_grid(painter, plot, palette)

        if self.model.has_frame:
            self._paint_histograms(painter, plot, palette)
            self._paint_clipping_cues(painter, plot)
        else:
            painter.setPen(text_color(palette, PLACEHOLDER_ALPHA))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "No camera feed")

        painter.setPen(QPen(palette.color(QPalette.ColorRole.Mid), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot)

        painter.end()

    def _paint_grid(self, painter, plot, palette):
        """Faint quarter lines, so levels and heights can be read off."""
        painter.setPen(QPen(text_color(palette, GRID_ALPHA), 1, Qt.PenStyle.DashLine))

        for fraction in GRID_FRACTIONS:
            x = plot.left() + plot.width() * fraction
            y = plot.top() + plot.height() * fraction

            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

    def _paint_histograms(self, painter, plot, palette):
        """Fill the luma histogram, or the three channels overlaid."""
        plotted = self.model.plotted_counts().astype(float)

        if self.model.log_y:
            plotted = np.log1p(plotted)

        # Scale to the tallest interior bin: a clipped end bin would flatten
        # everything else, and its cue already reports it.
        scale = plotted[:, 1:-1].max() or plotted.max() or 1.0
        heights = np.minimum(plotted / scale, 1.0) * plot.height()

        if len(plotted) == 1:
            fills = [text_color(palette, LUMA_FILL_ALPHA)]
        else:
            fills = [QColor(color) for color in LIVE_HISTOGRAM_CHANNEL_COLORS]

            for fill in fills:
                fill.setAlpha(CHANNEL_FILL_ALPHA)

            # Additive blending on a dark background, as on a camera's
            # screen: where all three channels overlap the fill turns white.
            if palette.color(QPalette.ColorRole.Base).lightness() < 128:
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Plus
                )

        painter.setPen(Qt.PenStyle.NoPen)

        for fill, series_heights in zip(fills, heights):
            painter.setBrush(fill)
            painter.drawPolygon(self._step_polygon(plot, series_heights))

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    @staticmethod
    def _step_polygon(plot, heights):
        """The outline of a step histogram of ``heights`` sitting on the
        plot's bottom edge."""
        bin_width = plot.width() / LIVE_HISTOGRAM_BINS
        bottom = plot.bottom()

        points = [QPointF(plot.left(), bottom)]

        for index, height in enumerate(heights):
            left = plot.left() + index * bin_width

            points.append(QPointF(left, bottom - height))
            points.append(QPointF(left + bin_width, bottom - height))

        points.append(QPointF(plot.right(), bottom))

        return QPolygonF(points)

    def _paint_clipping_cues(self, painter, plot):
        """Tint the darkest bin's column blue and the brightest one's red
        while enough pixels are clipped there."""

        cue_width = max(
            plot.width() / LIVE_HISTOGRAM_BINS, LIVE_HISTOGRAM_CLIP_CUE_MIN_WIDTH_PX
        )
        cues = (
            (self.model.clipped_low_pct, plot.left(), INFO_COLOR),
            (self.model.clipped_high_pct, plot.right() - cue_width, ERROR_COLOR),
        )

        for clipped_pct, left, color in cues:
            if clipped_pct <= LIVE_HISTOGRAM_CLIP_WARN_PCT:
                continue

            fill = QColor(color)
            fill.setAlpha(CLIP_CUE_ALPHA)

            painter.fillRect(QRectF(left, plot.top(), cue_width, plot.height()), fill)


class _LiveHistogramPlotEditor(QtEditor):
    """Host the plot; repaint it whenever what it shows changes."""

    def init(self, parent):
        self.control = LiveHistogramWidget(self.object)

    def update_editor(self):
        self._repaint()

    @observe("object:[channel_counts, channel_mode, log_y, has_frame]")
    def _repaint_on_model_change(self, event):
        self._repaint()

    def _repaint(self):
        if self.control is not None:
            self.control.update()


class LiveHistogramPlotEditor(BasicEditorFactory):
    """Editor factory for the live histogram plot; edit the ``counts`` trait
    of a LiveHistogramModel with it."""

    klass = _LiveHistogramPlotEditor
