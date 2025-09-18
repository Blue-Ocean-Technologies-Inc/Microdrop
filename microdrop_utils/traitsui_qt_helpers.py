from typing import Any

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyledItemDelegate
from traitsui.table_column import ObjectColumn

from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_VISIBILITY, ICON_VISIBILITY_OFF


class ColorRenderer(QStyledItemDelegate):
    def paint(self, painter, option, index):
        value = index.data()
        color = QColor(value)

        painter.save()

        # Draw the rectangle with the given color
        rect = option.rect
        painter.setBrush(color)
        painter.setPen(color)
        painter.drawRect(rect)

        painter.restore()


class ColorColumn(ObjectColumn):
    def __init__(self, **traits):  # Stolen from traitsui/extra/checkbox_column.py
        """Initializes the object."""
        super().__init__(**traits)

        # force the renderer to be our color renderer
        self.renderer = ColorRenderer()


class VisibleColumn(ObjectColumn):
    def __init__(self, **traits: Any):
        super().__init__(**traits)
        self.format_func = self.formatter
        self.text_font = QFont(ICON_FONT_FAMILY, 15)

    def formatter(self, value):  # No self since were just passing it as a function
        return ICON_VISIBILITY if value else ICON_VISIBILITY_OFF

    def on_click(self, object):
        object.visible = not object.visible