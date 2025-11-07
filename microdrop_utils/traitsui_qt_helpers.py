from typing import Any

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyledItemDelegate
from traits.trait_types import self
from traitsui.table_column import ObjectColumn
from traits.api import Str, Instance

from traitsui.api import RangeEditor

import logger
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


######## We have to define a new range column to properly handle range traits with spin boxes ########
class RangeColumn(ObjectColumn):
    editing_object_key = Str

    def __init__(self, **traits):
        super().__init__(**traits)
        self.editing_object_key = ""

        ### traitsui renders the static read-mode label and the editor labels
        ### when in edit-mode we have to check which row is edited and remove the static read-mode text
        self.format_func = self.formatter

    def formatter(self, value, object):  # No self since were just passing it as a function
        if object.key == self.editing_object_key:
            return ""
        return value

    def get_editor(self, object):
        """Gets the editor for the column of a specified object."""
        if self.editor is not None:
            return self.editor

        ### the current edited row object key is set here
        self.editing_object_key = object.key

        ### We have to override the del method of the range editor so when the edit mode is exited and del is called,
        ### we indicate that none of the rows are edited by setting the editing_object_key to "".
        ### to do this we need to apss the reference of this "parent_column" object to the range editor

        ### This is a major hack!
        ### TODO: Figure out bettter way to do this.

        class _RangeEditor(RangeEditor):
            parent_column = Instance(RangeColumn)
            def __del__(self):
                self.parent_column.editing_object_key = ""

        editor = _RangeEditor(low=0, high=100, mode="spinner", parent_column=self)

        return editor

    def get_value(self, object):
        """Gets the formatted value of the column for a specified object."""
        try:
            if self.format_func is not None:
                return self.format_func(self.get_raw_value(object), object)

            return self.format % (self.get_raw_value(object),)
        except:
            logger.exception(
                "Error occurred trying to format a %s value"
                % self.__class__.__name__
            )
            return "Format!"