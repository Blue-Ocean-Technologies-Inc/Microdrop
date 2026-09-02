# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Floating icon-button strip parked beside a zone selection or region on
the device view (a plain widget over the view's viewport, not a scene item,
so it never scales with the zoom)."""

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import QHBoxLayout, QToolButton, QWidget

# Microdrop style imports.
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import DEFAULT_GLYPH_POINT_SIZE_PX

# Local imports.
from ...consts import ZONE_OVERLAY_MARGIN_PX


class ZoneOverlayStrip(QWidget):
    """``button_specs``: iterable of (glyph, tooltip, on_clicked)."""

    def __init__(self, viewport, button_specs):
        super().__init__(viewport)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        for glyph, tooltip, on_clicked in button_specs:
            button = QToolButton(self)
            button.setText(glyph)
            button.setFont(QFont(ICON_FONT_FAMILY, DEFAULT_GLYPH_POINT_SIZE_PX))
            button.setToolTip(tooltip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(on_clicked)
            layout.addWidget(button)
        self.hide()

    def place_at(self, view, anchor_scene_point):
        """Park just outside the anchor (an item's top-right corner),
        clamped to the viewport."""
        anchor = view.mapFromScene(anchor_scene_point)
        self.adjustSize()
        viewport_rect = view.viewport().rect()
        x = anchor.x() + ZONE_OVERLAY_MARGIN_PX
        y = anchor.y() - self.height() - ZONE_OVERLAY_MARGIN_PX
        x = min(max(x, 0), max(viewport_rect.width() - self.width(), 0))
        y = min(max(y, 0), max(viewport_rect.height() - self.height(), 0))
        self.move(x, y)
        self.show()
        self.raise_()
