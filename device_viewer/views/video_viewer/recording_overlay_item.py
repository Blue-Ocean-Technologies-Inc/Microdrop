# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The device outline and actuated electrodes of a recording's overlay
sidecar, drawn in scene coordinates the way ElectrodeView draws the live
device. The playback canvas shows it as a scene item; the aligned export
calls its paint directly on every warped frame, so both look the same."""

# Enthought library imports.
from pyface.qt.QtCore import QPointF, QRectF
from pyface.qt.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from pyface.qt.QtWidgets import QGraphicsItem

# Local imports.
from ...default_settings import ELECTRODE_LINE, ELECTRODE_ON
from ..electrode_view.electrodes_view_base import ElectrodeView


class RecordingOverlayItem(QGraphicsItem):
    """Paints a RecordingOverlayTimeline's device: every electrode outline
    and the inner actuation fill of the actuated channels, each layer at
    its own opacity (0 hides it)."""

    def __init__(self, overlay, parent=None):
        super().__init__(parent)

        #: (channel, outline path, inner actuation path) per electrode.
        self._electrode_paths = []
        bounding_rect = QRectF()

        for electrode in overlay.device.get("electrodes", []):
            outline = QPainterPath()
            outline.addPolygon(
                QPolygonF([QPointF(x, y) for x, y in electrode["points"]])
            )
            outline.closeSubpath()

            self._electrode_paths.append(
                (
                    electrode["channel"],
                    outline,
                    ElectrodeView.create_inner_path(outline),
                )
            )
            bounding_rect = bounding_rect.united(outline.boundingRect())

        # Room for the outline pen's half width.
        self._bounding_rect = bounding_rect.adjusted(-1, -1, 1, 1)

        #: (actuated channels, outline opacity, actuations opacity).
        self._display = (frozenset(), 0.0, 0.0)

    def set_display(self, actuated_channels, outline_opacity, actuations_opacity):
        """Show ``actuated_channels``; opacities are 0-1."""
        display = (frozenset(actuated_channels), outline_opacity, actuations_opacity)

        if display != self._display:
            self._display = display
            self.update()

    def boundingRect(self):
        return self._bounding_rect

    def paint(self, painter, option=None, widget=None):
        actuated_channels, outline_opacity, actuations_opacity = self._display

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if actuations_opacity:
            actuated_color = QColor(ELECTRODE_ON)
            actuated_color.setAlphaF(actuations_opacity)

            for channel, _outline, inner in self._electrode_paths:
                if channel in actuated_channels:
                    painter.fillPath(inner, actuated_color)

        if outline_opacity:
            line_color = QColor(ELECTRODE_LINE)
            line_color.setAlphaF(outline_opacity)
            pen = QPen(line_color, 1)

            for _channel, outline, _inner in self._electrode_paths:
                painter.strokePath(outline, pen)

        painter.restore()
